#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import select
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evdev import InputDevice, UInput, ecodes, list_devices
from evdev.events import InputEvent


@dataclass(frozen=True)
class Mapping:
    name: str
    button_codes: frozenset[int]
    keyboard_code: int | None
    paddle_code: int | None


@dataclass
class PendingButton:
    press_event: InputEvent
    press_time: float
    forwarded: bool = False
    release_event: InputEvent | None = None


@dataclass
class ActiveMapping:
    mapping: Mapping
    active_codes: set[int]


class Remapper:
    def __init__(
        self,
        source: InputDevice,
        mappings: list[Mapping],
        combo_window_ms: int,
        emit_keyboard: bool,
        emit_paddle_device: bool,
        verbose: bool,
    ) -> None:
        self.source = source
        self.mappings = mappings
        self.combo_window_s = combo_window_ms / 1000.0
        self.verbose = verbose

        # Clone the controller so applications continue to see a normal gamepad.
        self.virtual_gamepad = UInput.from_device(
            source,
            name=f"{source.name} Virtual",
            filtered_types=[ecodes.EV_SYN, ecodes.EV_MSC, ecodes.EV_FF, ecodes.EV_FF_STATUS],
        )

        keyboard_codes = sorted({m.keyboard_code for m in mappings if m.keyboard_code is not None})
        paddle_codes = sorted({m.paddle_code for m in mappings if m.paddle_code is not None})

        self.virtual_keyboard = (
            UInput({ecodes.EV_KEY: keyboard_codes}, name="TT MAX Paddle Hotkeys")
            if emit_keyboard and keyboard_codes
            else None
        )
        self.virtual_paddles = (
            UInput({ecodes.EV_KEY: paddle_codes}, name="TT MAX Virtual Paddles")
            if emit_paddle_device and paddle_codes
            else None
        )

        self.special_codes = {code for mapping in mappings for code in mapping.button_codes}
        self.pending: dict[int, PendingButton] = {}
        self.pending_order: list[int] = []
        self.physical_pressed: dict[int, int] = {}
        self.active_mapping: ActiveMapping | None = None

    def log(self, message: str) -> None:
        if self.verbose:
            print(message, file=sys.stderr)

    def emit_key_pulse(self, ui: UInput, code: int) -> None:
        ui.write(ecodes.EV_KEY, code, 1)
        ui.syn()
        ui.write(ecodes.EV_KEY, code, 0)
        ui.syn()

    def emit_mapping_output(self, mapping: Mapping) -> None:
        if self.virtual_keyboard is not None and mapping.keyboard_code is not None:
            self.emit_key_pulse(self.virtual_keyboard, mapping.keyboard_code)
        if self.virtual_paddles is not None and mapping.paddle_code is not None:
            self.emit_key_pulse(self.virtual_paddles, mapping.paddle_code)

    def forward_event(self, event: InputEvent) -> None:
        self.virtual_gamepad.write_event(event)
        self.virtual_gamepad.syn()

    def flush_pending(self, force: bool = False) -> None:
        now = time.monotonic()
        for code in list(self.pending_order):
            pending = self.pending.get(code)
            if pending is None or pending.forwarded:
                continue
            if not force and now - pending.press_time < self.combo_window_s:
                continue

            # The remapper only suppresses a candidate combo while it still might
            # become one of the configured sentinels. If the combo window passes,
            # the original input is forwarded unchanged.
            self.forward_event(pending.press_event)
            pending.forwarded = True
            if pending.release_event is not None:
                self.forward_event(pending.release_event)
                del self.pending[code]

        self.pending_order = [code for code in self.pending_order if code in self.pending]

    def pressed_special_codes(self) -> set[int]:
        return {
            code
            for code, state in self.physical_pressed.items()
            if state and code in self.special_codes and code in self.pending
        }

    def maybe_trigger_mapping(self) -> bool:
        active_codes = self.pressed_special_codes()
        if not active_codes:
            return False

        for mapping in self.mappings:
            if mapping.button_codes != active_codes:
                continue

            newest_press = max(self.pending[code].press_time for code in mapping.button_codes)
            oldest_press = min(self.pending[code].press_time for code in mapping.button_codes)
            if newest_press - oldest_press > self.combo_window_s:
                continue

            # Swallow the sentinel buttons once the configured combo is complete,
            # then emit the remapped keyboard/paddle output exactly once.
            for code in mapping.button_codes:
                self.pending.pop(code, None)
            self.pending_order = [code for code in self.pending_order if code not in mapping.button_codes]
            self.active_mapping = ActiveMapping(mapping=mapping, active_codes=set(mapping.button_codes))
            self.log(f"Triggered {mapping.name}")
            self.emit_mapping_output(mapping)
            return True

        return False

    def handle_special_key(self, event: InputEvent) -> None:
        code = event.code
        self.physical_pressed[code] = event.value

        if self.active_mapping and code in self.active_mapping.active_codes:
            if event.value == 0:
                self.active_mapping.active_codes.discard(code)
                if not self.active_mapping.active_codes:
                    self.active_mapping = None
            return

        pending = self.pending.get(code)
        if event.value == 1:
            self.pending[code] = PendingButton(press_event=event, press_time=time.monotonic())
            self.pending_order.append(code)
            self.maybe_trigger_mapping()
            return

        if event.value == 2:
            if pending and pending.forwarded:
                self.forward_event(event)
            return

        if event.value == 0 and pending is not None:
            if pending.forwarded:
                self.forward_event(event)
                del self.pending[code]
            else:
                pending.release_event = event
            return

        self.forward_event(event)

    def run(self) -> None:
        self.log(f"Grabbing {self.source.path} ({self.source.name})")
        self.source.grab()
        try:
            while True:
                self.flush_pending()
                timeout = self.combo_window_s / 2.0 if self.pending else None
                ready, _, _ = select.select([self.source.fd], [], [], timeout)
                if not ready:
                    continue

                for event in self.source.read():
                    if event.type == ecodes.EV_SYN:
                        continue

                    if event.type == ecodes.EV_KEY and event.code in self.special_codes:
                        self.handle_special_key(event)
                    else:
                        self.flush_pending()
                        self.forward_event(event)
        finally:
            self.flush_pending(force=True)
            self.source.ungrab()
            self.virtual_gamepad.close()
            if self.virtual_keyboard is not None:
                self.virtual_keyboard.close()
            if self.virtual_paddles is not None:
                self.virtual_paddles.close()


def code_from_name(name: str) -> int:
    try:
        return ecodes.ecodes[name]
    except KeyError as exc:
        raise ValueError(f"Unknown evdev code: {name}") from exc


def load_config(path: Path) -> tuple[str, int, bool, bool, list[Mapping]]:
    raw = json.loads(path.read_text())
    mappings = []
    for item in raw["mappings"]:
        mappings.append(
            Mapping(
                name=item["name"],
                button_codes=frozenset(code_from_name(name) for name in item["buttons"]),
                keyboard_code=code_from_name(item["keyboard"]) if item.get("keyboard") else None,
                paddle_code=code_from_name(item["paddle_button"]) if item.get("paddle_button") else None,
            )
        )

    return (
        raw.get("device_name_contains", "GuliKit XW Controller"),
        int(raw.get("combo_window_ms", 35)),
        bool(raw.get("emit_keyboard", True)),
        bool(raw.get("emit_paddle_device", True)),
        mappings,
    )


def list_input_devices() -> int:
    for device_path in list_devices():
        device = InputDevice(device_path)
        print(f"{device_path}: {device.name}")
    return 0


def find_source_device(name_substring: str) -> InputDevice:
    matches = []
    for device_path in list_devices():
        device = InputDevice(device_path)
        if name_substring.lower() in device.name.lower():
            matches.append(device)

    if not matches:
        raise RuntimeError(f"No input device matched {name_substring!r}")

    # Prefer event devices that already look like gamepads.
    matches.sort(key=lambda device: (ecodes.EV_ABS not in device.capabilities(), device.path))
    return matches[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Translate TT MAX APG sentinel combos into host-side hotkeys "
            "or BTN_TRIGGER_HAPPY paddle buttons."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("tools/ttmax-config.example.json"),
        help="Path to the remapper config JSON",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List local input devices and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print device and trigger logs to stderr",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_devices:
        return list_input_devices()

    device_name_contains, combo_window_ms, emit_keyboard, emit_paddle_device, mappings = load_config(
        args.config
    )
    source = find_source_device(device_name_contains)

    remapper = Remapper(
        source=source,
        mappings=mappings,
        combo_window_ms=combo_window_ms,
        emit_keyboard=emit_keyboard,
        emit_paddle_device=emit_paddle_device,
        verbose=args.verbose,
    )

    def stop_handler(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        remapper.run()
    except KeyboardInterrupt:
        return 0
    except PermissionError as exc:
        print(
            "Permission denied while opening or grabbing the controller. "
            "Run the daemon with sudo or equivalent input/uinput access.",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - this is CLI safety net output
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
