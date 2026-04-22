from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


FILE_SIZE = 1024 * 1024
RECORD_SIZE = 18
CENTER = 2048
TRIGGER_MAX = 4095
STEP_DELAY_SCALE_NUM = 79
STEP_DELAY_SCALE_DEN = 1000
TIME_COUNTER_START = 11
TIME_COUNTER_INCREMENT = 14
TIME_COUNTER_MAX = 0xFFFF
RECORD_CONSTANT = 0x02

FACE_MASKS = {
    "PC": {"A": 0x02, "B": 0x01, "X": 0x08, "Y": 0x04},
    "Switch": {"A": 0x01, "B": 0x02, "X": 0x04, "Y": 0x08},
}

BUTTON_MASK_1 = {
    "LB": 0x10,
    "RB": 0x20,
    "LT": 0x40,
    "RT": 0x80,
}

BUTTON_MASK_2 = {
    "R3": 0x01,
    "L3": 0x02,
    "START": 0x04,
    "SELECT": 0x08,
    "HOME": 0x10,
}

D_PAD_VALUES = {
    "D_UP": 0x01,
    "D_UP_RIGHT": 0x02,
    "D_RIGHT": 0x03,
    "D_DOWN_RIGHT": 0x04,
    "D_DOWN": 0x05,
    "D_DOWN_LEFT": 0x06,
    "D_LEFT": 0x07,
    "D_UP_LEFT": 0x08,
}

STICK_IDS = {"L_STICK", "R_STICK"}
STICK_DIRECTIONS = {"UP", "DOWN", "LEFT", "RIGHT"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a GuliKit Auto.apg file using the same record layout and timing "
            "rules as the official macro editor."
        )
    )
    parser.add_argument("config", type=Path, help="Path to an editor-style APG JSON config")
    parser.add_argument("output", type=Path, help="Path to write Auto.apg")
    parser.add_argument(
        "--layout",
        choices=("PC", "Switch"),
        help="Override the ABXY layout from the config file",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    raw = json.loads(path.read_text())
    if "macroList" not in raw or not isinstance(raw["macroList"], list):
        raise RuntimeError("Config must contain a top-level 'macroList' array")
    return raw


def clamp_percent(value: int) -> int:
    return max(0, min(100, value))


def scale_stick_value(value: int) -> int:
    return math.floor((clamp_percent(value) / 100.0) * 2047)


def write_u16le(buf: bytearray, offset: int, value: int) -> None:
    buf[offset] = (value >> 8) & 0xFF
    buf[offset + 1] = value & 0xFF


def normalize_layout(config: dict, override: str | None) -> str:
    if override:
        return override
    layout = config.get("abxyLayout", "Switch")
    if layout not in FACE_MASKS:
        raise RuntimeError(f"Unsupported ABXY layout: {layout!r}")
    return layout


def build_record(step: dict, layout: str, time_counter: int) -> bytes:
    left_x = CENTER
    left_y = CENTER
    right_x = CENTER
    right_y = CENTER
    lt = 0
    rt = 0
    button_mask_1 = 0
    button_mask_2 = 0
    d_pad = 0

    if not step.get("isBlankDelay", False):
        for stick in step.get("sticks", []):
            stick_id = stick.get("id")
            direction = stick.get("direction")
            value = scale_stick_value(int(stick.get("value", 0)))

            if stick_id not in STICK_IDS or direction not in STICK_DIRECTIONS:
                continue

            if stick_id == "L_STICK":
                if direction == "UP":
                    left_y = CENTER + value
                elif direction == "DOWN":
                    left_y = CENTER - value
                elif direction == "LEFT":
                    left_x = CENTER - value
                elif direction == "RIGHT":
                    left_x = CENTER + value
            elif stick_id == "R_STICK":
                if direction == "UP":
                    right_y = CENTER + value
                elif direction == "DOWN":
                    right_y = CENTER - value
                elif direction == "LEFT":
                    right_x = CENTER - value
                elif direction == "RIGHT":
                    right_x = CENTER + value

        for button in step.get("buttons", []):
            button_id = button.get("id")

            if button_id in FACE_MASKS[layout]:
                button_mask_1 |= FACE_MASKS[layout][button_id]
            if button_id in BUTTON_MASK_1:
                button_mask_1 |= BUTTON_MASK_1[button_id]
            if button_id in BUTTON_MASK_2:
                button_mask_2 |= BUTTON_MASK_2[button_id]
            if button_id in D_PAD_VALUES:
                d_pad = D_PAD_VALUES[button_id]

        if any(button.get("id") == "LT" for button in step.get("buttons", [])):
            lt = TRIGGER_MAX
        if any(button.get("id") == "RT" for button in step.get("buttons", [])):
            rt = TRIGGER_MAX

    record = bytearray(RECORD_SIZE)
    write_u16le(record, 0, left_x)
    write_u16le(record, 2, left_y)
    write_u16le(record, 4, right_x)
    write_u16le(record, 6, right_y)
    write_u16le(record, 8, lt)
    write_u16le(record, 10, rt)
    record[12] = button_mask_1
    record[13] = button_mask_2
    record[14] = d_pad
    record[15] = RECORD_CONSTANT
    record[16] = (time_counter >> 8) & 0xFF
    record[17] = time_counter & 0xFF
    return bytes(record)


def generate_apg(config: dict, layout: str) -> bytes:
    data = bytearray(b"\xFF" * FILE_SIZE)
    time_counter = TIME_COUNTER_START
    record_index = 0
    max_records = FILE_SIZE // RECORD_SIZE

    for step in config["macroList"]:
        repeat_count = round((int(step.get("delay", 0)) * STEP_DELAY_SCALE_NUM) / STEP_DELAY_SCALE_DEN)
        for _ in range(repeat_count):
            if record_index >= max_records:
                return bytes(data)

            if record_index > 0:
                time_counter += TIME_COUNTER_INCREMENT
                if time_counter > TIME_COUNTER_MAX:
                    time_counter = 0

            offset = record_index * RECORD_SIZE
            data[offset : offset + RECORD_SIZE] = build_record(step, layout, time_counter)
            record_index += 1

    return bytes(data)


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    layout = normalize_layout(config, args.layout)
    data = generate_apg(config, layout)
    args.output.write_bytes(data)

    print(f"layout={layout}")
    print(f"records_written={sum(1 for i in range(0, FILE_SIZE, RECORD_SIZE) if data[i] != 0xFF)}")
    print(f"output_file={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
