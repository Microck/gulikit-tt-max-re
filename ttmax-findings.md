# TT MAX Paddle Findings

## Bottom line

The stock TT MAX firmware does **not** expose the rear paddles as separate `P1`-`P4` inputs in any official flow I found.

The strongest official evidence points to this model instead:

- Rear paddles `G1`-`G4` can map only to existing controller buttons.
- The controller exposes a single shared `Auto.apg` file through USB storage mode.
- The official manual explicitly says `All 4 back buttons have a 30-second APG function.`
- APG files can be backed up and restored through the controller's USB storage mode.

That means there are two realistic paths:

1. Patch the firmware so the controller emits extra HID buttons. This is the cleanest end state, but it needs the real firmware package, device traces, and a much riskier RE loop.
2. Use the existing APG feature as a transport and translate it on the host. This is now officially supported on all four back buttons, even though the inner layout of the shared `Auto.apg` file still needs more RE.

The host-side path is the one that survives firmware changes best, because it depends only on features GuliKit already ships: APG playback, APG file backup, and normal controller output.

The native firmware path is now better grounded than before because teardown evidence confirms a central `GP3F128` package and a dedicated rear-button PCB. It still does **not** unlock a safe native patch because the update `.bin` remains an opaque, fully rewrapped container.

The current host-side identity model is also stronger now:

- cached `USB\\VID_045E&PID_028E\\000001` shows `Xbox 360 Controller for Windows`
- cached `USB\\VID_057E&PID_2009\\...` shows `Pro Controller`
- confirmed updater mode shows `USB\\VID_34D3&PID_1100`
- all three live in the same Windows port location: `Port_#0007.Hub_#0001`

That makes a three-personality controller model plausible:

1. XInput mode
2. Switch / Pro Controller mode
3. update-mode mass-storage stub

The official manual now backs that direction up at the product level:

- the `Mode` button `double-click` switches modes
- the manual distinguishes `PC mode` and `NS mode`
- Bluetooth pairing in PC mode uses the name `GuliKit XW Controller`

For a native `P1` to `P4` patch, that matters because XInput is not a friendly target for new native buttons. The more realistic native lane is to understand and alter the Switch / HID personality or to introduce a new composite behavior, which is materially harder than just changing a rear-button mapping table.

## Official evidence

### Product page

The official TT MAX / PRO page advertises:

- `4 Metal Rear Paddles`
- `Patented APG(Auto-Pilot Gaming) Functionality`

It does **not** advertise separate rear-button HID outputs or a developer-facing paddle mode.

Source:

- [TT MAX / PRO product page](https://www.gulikit.com/productinfo/3600562.html)

### Manual

The official TT MAX manual is explicit:

- `Back Button Mapping: Settings button + Back button`
- `Press the button you want to map.`
- `The back buttons can only map to have normal key function and do not support Continuous Fire feature.`

It also says:

- `Back Button (Auto Pilot Gaming) APG Function`
- `APG button + Back button ...`
- `Single Playback: Short press the Back button.`
- `All 4 back buttons have a 30-second APG function.`
- `APG Recording File Share` exposes a USB drive named `GuliKit dat`
- The APG file inside that drive is `Auto.apg`

Source:

- [TT MAX manual](https://www.gulikit.com/filedownload/2978168)

### Firmware notes

The official V6.8 firmware notes say:

- `Fixed an issue where occasional joystick jitter occurred when mixing APG and button mapping functions on the rear buttons.`

That reinforces the model above: rear buttons support button mapping and APG, not a hidden official `P1`-`P4` mode. Combined with the manual, it does prove that all four rear paddles support APG playback, but it still does **not** prove how those four paddle-specific APG payloads are packed inside `Auto.apg`.

Source:

- [TT MAX / TT PRO V6.8 firmware page](https://gulikit.com/newsinfo/3137265.html)

## APG file RE result

I now have a real `Auto.apg` artifact from a live TT MAX in APG sharing mode.

What is confirmed:

- file size is exactly `1048576` bytes
- a blank APG file is all `0xFF`
- GuliKit's official web editor generates the same `1 MiB` layout
- the editor writes fixed-size `18-byte` records for non-blank steps

What is **not** yet confirmed:

- how the four paddle-specific APG payloads are encoded inside the shared `Auto.apg` file

The official manual documents two APG layers:

- controller-wide APG record/playback through the `Learn` and `APG` buttons
- rear-button APG playback through `APG + Back button`, with `All 4 back buttons have a 30-second APG function`

What is still missing is the file-level mapping from those four rear-button APG actions into the single `Auto.apg` artifact.

## Native firmware evidence got stronger

I now have preserved teardown artifacts under `artifacts/teardown-video/`.

What those artifacts add:

- the TT MAX teardown stills show a central package marked `GuliKit GP3F128 2533`
- the teardown transcript describes that package as the likely main control MCU
- the rear paddles are not wired individually into the shell; they sit on a small daughterboard that mates to the mainboard through spring contacts
- the likely RF chip sits near the PCB antenna, which supports a split between a main control chip and a separate radio path

Cross-source corroboration now ties that chip marking to GuliKit's broader controller line:

- a mirrored KK3 manual explicitly calls `GP3F128` a customized `Gpower` CPU
- a mirrored KK3 Max page describes a `custom GuliKit GP3F128 chip`
- a GuliKit X post for the KK3 line markets the `Gpower CPU` alongside `1000Hz` wired polling

That matters because it makes the native path less speculative. The strongest working model now is that TT MAX is another member of the same GuliKit `GP3F128` platform family as the KK3 line, not a totally separate mystery controller.

What is still blocked:

- the TT update blobs still look like opaque containers rather than plain flash images
- adjacent TT MAX versions share `0` identical aligned `8`, `16`, or `32` byte blocks
- adjacent TT MAX versions also share `0` unique `8`, `16`, or `32` byte blocks anywhere in the file
- the captured update trace contains only standard MSC traffic: `Write(10)`, `Test Unit Ready`, `Prevent/Allow Medium Removal`, and `Request Sense`
- `Prevent/Allow Medium Removal` fails with `Illegal Request / Invalid Command Operation Code`, which makes the updater look like a very thin fake-disk implementation rather than a full MSC stack
- Windows PnP properties brand the updater stub as `Gulikit X`, but still do not reveal the TT MAX normal-mode VID/PID
- the old `3554:F507` and `3554:F508` leads are now doubly disqualified because their cached bus-reported device description is `X2H Mini`
- the strongest current normal-mode lead is now `USB\\VID_057E&PID_2009` with bus-reported description `Pro Controller` on the same physical port as the confirmed updater stub, which fits the observed Windows behavior but is still not a live isolated descriptor capture
- cached `USB\\VID_045E&PID_028E\\000001` on that same port now makes an XInput personality plausible too

That block-level result is why I still cannot responsibly claim a native `P1` to `P4` firmware patch.

There is also now a real documentation conflict around update-mode entry:

- the official V6.8 page says `APG + Home`
- AKNES's NS69 FAQ says `APG + A`
- a Scribd mirror of the upgrade guide also says `APG + A`

So even the boot-mode entry path is not yet fully cleanly documented across sources.

## What the daemon does

`tools/ttmax-paddle-daemon.py` is a Linux-only remapper that:

1. grabs the physical TT MAX input device
2. mirrors it to a virtual gamepad
3. watches for configured APG sentinel combos
4. swallows those combos before games see them
5. emits replacement outputs such as `F13`-`F16` and `BTN_TRIGGER_HAPPY1`-`4`

That is the key detail. Because the daemon grabs the physical device, the weird sentinel combo does not leak into the game if it matches a configured rear-paddle signature.

`tools/apply-firmware-patch.py` is also stronger now as a future native-patch vehicle. It supports:

- input hash verification
- exact-byte preconditions
- deterministic in-place replacement
- signature-based anchors via `find_hex`
- wildcard bytes in signature anchors
- relative patch offsets from a matched anchor
- exact match-count verification so a future update does not silently patch the wrong region

## Re-apply after firmware updates

This is the durable part of the design.

1. Build or capture the `Auto.apg` file you want.
2. Enter APG file share mode on the controller with `SETUP + APG` while it is powered on and connected by USB.
3. Back up `Auto.apg`.
4. Keep that APG file somewhere safe.
5. After a firmware update or reset, restore `Auto.apg` back onto the controller.

So even if GuliKit wipes controller state during a firmware update, the controller-side part is just an `Auto.apg` restore.

## Firmware-RE path if you still want native `P1`-`P4`

If the goal is true extra HID buttons emitted by the controller itself, the next loop is:

1. Keep using `artifacts/teardown-video/` as the hardware baseline for the `GP3F128` platform.
2. Recover older TT packages, a bootloader dump, or a post-copy commit trace that exposes the inner container semantics.
3. Use `binwalk`, Ghidra, and container-diff tooling only after the wrapper is understood well enough to recover a real code image.
4. Trace USB/HID report descriptors and button-mapping tables in the recovered image.
5. Patch the HID descriptor and report packing to add four buttons.
6. Rewrap the modified image into a valid update container.
7. Reflash and verify on Linux with `evtest` and `hid-recorder`.

That is feasible RE work, but not responsibly flashable from this workspace until the container format and commit path are real, not guessed.

## Additional external findings

- FCC ID `2BLVF-NS69` confirms the regulatory identity of the TT MAX controller and exposes public filing buckets for BLE, antenna, label/location, and test setup photos, but no public internal board photos or GP3F128 details.
- AKNES's NS69 FAQ says its `Revision` hardware specifically addressed rear-button hardware issues found during community testing, which matches community reports of rear-button tactility problems and early-hardware churn.
- GuliKit's announced mobile app for TT / ES / Elves 2 support is still only announced for `Q2 2026`; there is no confirmed official Android or iOS release to reverse engineer yet.

## Reverse-engineering tools worth using from the RE tools list

From `https://github.com/stars/nubbsterr/lists/re-tools`, the directly relevant tools for this controller job are:

- `ReFirmLabs/binwalk` for firmware container triage
- `mrphrazer/ghidra-headless-mcp` or local Ghidra for disassembly
- `huettenhain/ghidradark` only if you want a themed Ghidra setup

The list also contains general RE/AI tooling, but the controller-specific loop here is mostly `binwalk + Ghidra + HID capture`.

## Running the daemon

### Install dependencies

```bash
uv sync
```

### Inspect devices

```bash
uv run python tools/ttmax-paddle-daemon.py --list-devices
```

### Run the remapper

```bash
sudo uv run python tools/ttmax-paddle-daemon.py --config tools/ttmax-config.example.json --verbose
```

### What to bind in software

You can bind either:

- `F13` to `F16`
- `BTN_TRIGGER_HAPPY1` to `BTN_TRIGGER_HAPPY4`

Use whichever target your stack sees more reliably.

## Limits

- This implementation is Linux-first.
- It does not generate APG files directly yet.
- It assumes the rear paddles can trigger APG playback consistently on PC, which matches the manual and firmware notes.
- It is intentionally not a firmware flasher or patcher.
