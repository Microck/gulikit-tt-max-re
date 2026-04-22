# GuliKit TT MAX Reverse Engineering

research and tooling for reverse engineering the **GuliKit TT MAX** (`NS69`) controller, with a focus on native rear-paddle support and firmware/update behavior.

## Status

- Native `P1`–`P4` paddle patch is **not solved**
- TT MAX exposes multiple personalities on Windows:
  - `045E:028E` — Xbox 360 Controller for Windows
  - `057E:2009` — Nintendo Pro Controller
  - `34D3:1100` — update-mode mass-storage stub
- Official TT firmware blobs remain opaque wrapped containers, not plain flash images

## What Is Here

**Research notes:**

| File | Content |
|------|---------|
| [`ttmax-findings.md`](ttmax-findings.md) | Core findings: paddle behavior, APG file format, HID identity model |
| [`ttmax-native-firmware.md`](ttmax-native-firmware.md) | Firmware analysis: update container format, board layout, GP3F128 teardown |
| [`ttmax-apg-format.md`](ttmax-apg-format.md) | APG file format reverse engineering |

**Tools** (in [`tools/`](tools/)):

| Tool | Purpose |
|------|---------|
| `ttmax-paddle-daemon.py` | Host-side rear paddle remapper using APG sentinel combos |
| `download-gulikit-file.py` | Download firmware files from GuliKit servers |
| `ocr-gulikit-captcha.py` | OCR helper for GuliKit download captchas |
| `scan-gulikit-file-ids.py` | Enumerate downloadable file IDs |
| `analyze-ttmax-firmware.py` | Parse and diff TT MAX firmware blobs |
| `apply-firmware-patch.py` | Apply binary patches to firmware images |
| `extract-usbms-writes.py` | Extract USB mass-storage write traces from pcaps |
| `ttmax-hid-probe.py` | Probe HID descriptors and registry entries on Windows |
| `inspect-apg-file.py` | Inspect and dump APG file structure |
| `generate-apg-file.py` | Generate APG configuration files |

**Artifacts** (in [`artifacts/`](artifacts/)):

- Teardown photos and video captions
- USB capture traces
- Update session logs

## What Is Not Here

- A working native firmware patch
- Any claim that the controller already exposes true native `P1`–`P4`
- A guaranteed safe flashing workflow for modified TT firmware

### Configuration

Copy the example config and adjust for your setup:

```bash
cp tools/ttmax-config.example.json tools/ttmax-config.json
```

See `ttmax-config.example.json` for configuration options.

## Usage

### Paddle Daemon

Run the host-side rear paddle remapper:

```bash
python tools/ttmax-paddle-daemon.py --config tools/ttmax-config.json
```

### Firmware Analysis

Download and analyze firmware blobs:

```bash
python tools/download-gulikit-file.py --file-id <ID> --output firmware.bin
python tools/analyze-ttmax-firmware.py firmware.bin
```

### APG File Operations

Inspect or generate APG configuration files:

```bash
python tools/inspect-apg-file.py artifacts/ttmax-auto.apg
python tools/generate-apg-file.py --config tools/apg-config.example.json --output output.apg
```

### USB Trace Extraction

Extract USB mass-storage writes from a pcap capture:

```bash
python tools/extract-usbms-writes.py artifacts/ttmax-v68-update-usbpcap1.pcapng
```

## Architecture

The project follows two parallel investigation paths:

1. **Host-side remapping** — Uses the controller's existing APG feature as a transport, translating paddle presses on the host. Survives firmware changes because it depends only on features GuliKit already ships.

2. **Native firmware patching** — Patch the firmware so the controller emits extra HID buttons. Requires understanding the opaque update container format and the GP3F128 chip's flash layout. Higher risk but cleaner end state.
