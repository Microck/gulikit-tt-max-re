# TT MAX APG Format Notes

## Verified controller-side flows

- APG sharing mode entry on TT series:
  - controller powered on
  - connected by USB
  - hold `SETUP/Gear + APG`
- APG sharing volume label: `GuliKit dat`
- APG sharing file name: `Auto.apg`
- TT clear-all-settings reset:
  - hold `Settings + +`
  - controller gives a long vibration when reset completes

These were verified from GuliKit's official TT manual and APG editor announcement.

## Verified file properties

From a live TT MAX in APG sharing mode:

- size: `1048576` bytes
- blank file hash:
  - `f5fb04aa5b882706b9309e885f19477261336ef76a150c3b4d3489dfac3953ec`
- blank file contents:
  - all `0xFF`
- tail:
  - the final `4` bytes are `0xFF`

From the official `macro.gulikit.com` editor:

- generated file size is also `1048576` bytes
- generated data is written as fixed `18-byte` records
- unused record space is filled with `0xFF`

## Record layout

Each non-blank record is `18` bytes:

1. `0x00..0x01` left stick X, big-endian 16-bit, centered at `2048`
2. `0x02..0x03` left stick Y, big-endian 16-bit, centered at `2048`
3. `0x04..0x05` right stick X, big-endian 16-bit, centered at `2048`
4. `0x06..0x07` right stick Y, big-endian 16-bit, centered at `2048`
5. `0x08..0x09` left trigger, big-endian 16-bit, `0` or `4095`
6. `0x0A..0x0B` right trigger, big-endian 16-bit, `0` or `4095`
7. `0x0C` button mask 1
8. `0x0D` button mask 2
9. `0x0E` d-pad hat value
10. `0x0F` constant byte `0x02`
11. `0x10..0x11` time counter, big-endian 16-bit

## Timing rules from the official editor

- step repeat count:
  - `round(delay_ms * 79 / 1000)`
- initial time counter:
  - `11`
- per-record increment:
  - `14`
- wrap rule:
  - if the counter grows past `65535`, reset it to `0`

This is unusual, but the local generator matches the official editor byte-for-byte by following those same rules.

## Button masks

`button mask 1`

- face buttons depend on `abxyLayout`
- `LB = 0x10`
- `RB = 0x20`
- `LT = 0x40`
- `RT = 0x80`

`button mask 2`

- `R3 = 0x01`
- `L3 = 0x02`
- `START = 0x04`
- `SELECT = 0x08`
- `HOME = 0x10`

Face-button mapping:

- `PC` layout:
  - `B = 0x01`
  - `A = 0x02`
  - `Y = 0x04`
  - `X = 0x08`
- `Switch` layout:
  - `A = 0x01`
  - `B = 0x02`
  - `X = 0x04`
  - `Y = 0x08`

## D-pad values

- neutral: `0`
- `D_UP = 1`
- `D_UP_RIGHT = 2`
- `D_RIGHT = 3`
- `D_DOWN_RIGHT = 4`
- `D_DOWN = 5`
- `D_DOWN_LEFT = 6`
- `D_LEFT = 7`
- `D_UP_LEFT = 8`

## Local tools

- `tools/generate-apg-file.py`
  - builds `Auto.apg` from an editor-style JSON config
- `tools/inspect-apg-file.py`
  - decodes non-blank `18-byte` records from `Auto.apg`
- `tools/gulikit-apg-share.ps1`
  - waits for `GuliKit dat` and backs up or restores `Auto.apg` on Windows

## Current limitation

This reverse engineering work proves the APG file format is host-generatable and restorable after firmware updates.

The official TT MAX manual now resolves one important ambiguity:

- `Back Button (Auto Pilot Gaming) APG Function`
- `Single Playback: Short press the Back button.`
- `All 4 back buttons have a 30-second APG function.`

What remains unsolved is narrower:

- how those four rear-button APG payloads are encoded inside the shared `Auto.apg` file
