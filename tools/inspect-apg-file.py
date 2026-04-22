from __future__ import annotations

import argparse
import json
from pathlib import Path


FILE_SIZE = 1024 * 1024
RECORD_SIZE = 18

FACE_MASKS = {
    "PC": {0x01: "B", 0x02: "A", 0x04: "Y", 0x08: "X"},
    "Switch": {0x01: "A", 0x02: "B", 0x04: "X", 0x08: "Y"},
}

BUTTON_MASK_1 = {
    0x10: "LB",
    0x20: "RB",
    0x40: "LT",
    0x80: "RT",
}

BUTTON_MASK_2 = {
    0x01: "R3",
    0x02: "L3",
    0x04: "START",
    0x08: "SELECT",
    0x10: "HOME",
}

D_PAD_VALUES = {
    0x00: None,
    0x01: "D_UP",
    0x02: "D_UP_RIGHT",
    0x03: "D_RIGHT",
    0x04: "D_DOWN_RIGHT",
    0x05: "D_DOWN",
    0x06: "D_DOWN_LEFT",
    0x07: "D_LEFT",
    0x08: "D_UP_LEFT",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decode non-blank GuliKit Auto.apg records")
    parser.add_argument("apg", type=Path, help="Path to Auto.apg")
    parser.add_argument(
        "--layout",
        choices=("PC", "Switch"),
        default="PC",
        help="Interpret the ABXY face-button mask using this layout",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=64,
        help="Maximum number of decoded non-blank records to print",
    )
    return parser.parse_args()


def read_u16le(chunk: bytes, offset: int) -> int:
    return (chunk[offset] << 8) | chunk[offset + 1]


def decode_buttons(mask1: int, mask2: int, layout: str, dpad: int) -> list[str]:
    buttons: list[str] = []
    for bit, name in FACE_MASKS[layout].items():
        if mask1 & bit:
            buttons.append(name)
    for bit, name in BUTTON_MASK_1.items():
        if mask1 & bit:
            buttons.append(name)
    for bit, name in BUTTON_MASK_2.items():
        if mask2 & bit:
            buttons.append(name)
    dpad_name = D_PAD_VALUES.get(dpad)
    if dpad_name:
        buttons.append(dpad_name)
    return buttons


def decode_records(data: bytes, layout: str, limit: int) -> list[dict]:
    if len(data) != FILE_SIZE:
        raise RuntimeError(f"Unexpected APG file size: {len(data)}")

    records = []
    usable_bytes = len(data) - (len(data) % RECORD_SIZE)
    for index in range(0, usable_bytes, RECORD_SIZE):
        chunk = data[index : index + RECORD_SIZE]
        if chunk == b"\xFF" * RECORD_SIZE:
            continue

        mask1 = chunk[12]
        mask2 = chunk[13]
        dpad = chunk[14]
        records.append(
            {
                "record_index": index // RECORD_SIZE,
                "left_x": read_u16le(chunk, 0),
                "left_y": read_u16le(chunk, 2),
                "right_x": read_u16le(chunk, 4),
                "right_y": read_u16le(chunk, 6),
                "left_trigger": read_u16le(chunk, 8),
                "right_trigger": read_u16le(chunk, 10),
                "button_mask_1": mask1,
                "button_mask_2": mask2,
                "dpad": dpad,
                "constant": chunk[15],
                "time_counter": read_u16le(chunk, 16),
                "buttons": decode_buttons(mask1, mask2, layout, dpad),
            }
        )

        if len(records) >= limit:
            break

    return records


def main() -> int:
    args = parse_args()
    data = args.apg.read_bytes()
    records = decode_records(data, args.layout, args.limit)
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
