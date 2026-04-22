# TT MAX Native Firmware RE Status

## Current state

I acquired the official TT firmware package directly from GuliKit and extracted the two update images:

- `firmware/NS69_TT-MAX_V6.8.bin`
- `firmware/NS68_TT-PRO_V6.8.bin`

The TT MAX image characteristics are:

- size: `45920` bytes
- sha256: `9881bc7320fd2732afedbb69e781f7353fe441d923414a97861df8c5006b57d8`
- entropy: `7.9959`

The TT PRO image characteristics are:

- size: `44216` bytes
- sha256: `c04260ed1a2ff6fed072b4ccd883b72c0fa28c319929031ac6de7be50ee0a9b3`
- entropy: `7.9964`

I also acquired an official KK3 family package as a vendor-format comparison point:

- `NS39_KK3_MAX_V5.9.bin`
- `NS38_KK3_PRO_V5.8.bin`

Those images are also opaque:

- KK3 MAX size: `51500` bytes, sha256 `d1c7d485e1a29fd518d2a77c824c46a883bdd6c73c8126cca15bf5a1ec6d6ae4`, entropy `7.9968`
- KK3 PRO size: `51624` bytes, sha256 `433ae3fc2753c2308e047979c7eef1d0b6f48de472b7b86c76489fae4a934a30`, entropy `7.9968`

I now also have three TT firmware revisions side by side:

- `TT-MAX_TT-PRO_V6.6.zip`
- `TT-MAX_TT-PRO_V6.7.zip`
- `TT-MAX_TT-PRO_V6.8.zip`

Extracted TT MAX images:

- V6.6: `44288` bytes, sha256 `da3f06da87fab88ee701861d6690bcce1eb17948b69dc7f9e29b1e19c53ec9fb`
- V6.7: `45944` bytes, sha256 `1804b1e9f9ddff75847e785f5f603cbbe91cbf07e4ed26a360364b5456b4dc87`
- V6.8: `45920` bytes, sha256 `9881bc7320fd2732afedbb69e781f7353fe441d923414a97861df8c5006b57d8`

Extracted TT PRO images:

- V6.6: `42096` bytes, sha256 `1ebbb8123982b4468860d3219a9020547168120dfc31dc91f67a3530408be8e2`
- V6.7: `44260` bytes, sha256 `7bf349c70764a391eb81c7d8b53ebd62b62c512d20d44a1f65959feb11ca3f3c`
- V6.8: `44216` bytes, sha256 `c04260ed1a2ff6fed072b4ccd883b72c0fa28c319929031ac6de7be50ee0a9b3`

## What that means technically

These blobs are not exposing a plain Cortex-M flash image.

Evidence:

- `file` reports only opaque `data`
- printable ASCII islands are effectively absent
- no plausible Cortex-M vector table appears anywhere in the blobs
- same-position byte matches between TT MAX and TT PRO are only about `0.35%`
- XORing the two images still produces near-max entropy

That combination strongly suggests one of these:

1. encrypted update payloads
2. compressed-packed payloads with no obvious public header
3. signed containers with per-image randomization or authenticated wrapping

The KK3 comparison matters because it weakens the idea that TT MAX is a one-off weird blob. GuliKit appears to ship multiple controller families in the same kind of opaque, high-entropy update container.

The three-version TT comparison makes that conclusion stronger:

- TT MAX V6.6 -> V6.7 same-position byte matches: about `0.41%`
- TT MAX V6.7 -> V6.8 same-position byte matches: about `0.40%`
- TT PRO V6.6 -> V6.7 same-position byte matches: about `0.41%`
- TT PRO V6.7 -> V6.8 same-position byte matches: about `0.40%`
- same-version TT MAX vs TT PRO comparisons are also only about `0.35%` to `0.41%`
- common prefix is `0` bytes in most pairings and only `1` byte in a few same-version cross-product pairings
- XOR entropy stays near maximum in every tested pair
- adjacent TT MAX revisions share `0` identical aligned blocks at `8`, `16`, and `32` byte granularity
- adjacent TT MAX revisions also share `0` unique `8`, `16`, or `32` byte blocks anywhere in the file
- same-version TT MAX vs TT PRO comparisons also share `0` aligned and `0` shared unique blocks at those sizes
- individual TT images contain effectively no repeated aligned `8`, `16`, or `32` byte blocks either

This is not how a bare flash image behaves when a small feature changes. It is consistent with a per-build wrapped container where most of the blob is transformed again for each release.

One version-shape pattern does stand out:

- TT MAX grows by `1656` bytes from V6.6 to V6.7, then shrinks by `24` bytes in V6.8
- TT PRO grows by `2164` bytes from V6.6 to V6.7, then shrinks by `44` bytes in V6.8

That matches the public release notes reasonably well:

- V6.7 introduced the larger Dead Zone Mode 2.0 behavior change
- V6.8 looks like a smaller follow-up fix for rear-button/APG interaction

But the container still rewrites almost completely between those versions, so the delta is visible only in file size, not in any stable byte neighborhood.

I also installed `ReFirmLabs/binwalk` from the reverse-engineering tools list and ran it across all six TT images.

Result:

- no known embedded file signatures were detected in any TT V6.6, V6.7, or V6.8 `.bin`
- no extractable inner format was identified by stock binwalk signatures

That does not prove there is no inner payload. It does show that the container is not something simple and recognizable like a raw compressed stream, filesystem image, or obvious packed firmware format that binwalk already knows.

## Official file ID anchors

I now have several official `filedownload/<id>` anchors from GuliKit pages:

- Hyperlink 2 Wireless Controller Adapter PC05 V1.9, dated `2026-02-27`: `2990378`
- KK3 MAX / PRO V5.9, dated `2026-03-02`: `2990583`
- ES / ES PRO V3.8, dated `2026-03-06`: `2990881`
- TT MAX / TT PRO V6.8, dated `2026-04-13`: `2994052`

Those anchors put the missing TT V6.7 package, dated `2026-04-03`, roughly in the `29932xx` neighborhood if GuliKit's file IDs were allocated at a roughly steady rate across that period.

I have **not** recovered the exact V6.7 file ID yet.

## Teardown-derived hardware findings

I now have preserved teardown artifacts under `artifacts/teardown-video/`, including:

- translated captions from the teardown video
- raw caption XML from YouTube
- stills showing the mainboard, the central `GP3F128` package, and the rear-button PCB

What is now directly supported by those artifacts:

- the teardown identifies TT MAX as `NS69` and TT PRO as `NS68`
- `artifacts/teardown-video/mainboard-wide.jpg` and `artifacts/teardown-video/gp3f128.jpg` show a large central package marked `GuliKit GP3F128 2533`
- the teardown transcript describes that package as the likely main control MCU
- `artifacts/teardown-video/rear-pcb.jpg` and the transcript show that the four rear buttons live on a small daughterboard and connect back to the mainboard through spring contacts, not through loose wires
- the transcript places a likely wireless/RF chip next to the PCB antenna, but the package marking is still unreadable in the captured stills
- the battery label is `3.7V 950mAh`
- the measured standby current is `1.7 microamps`

Independent corroboration now exists outside the teardown:

- a mirrored KK3 manual states: `Powered by a customized "Gpower" CPU (GP3F128), ensuring high precision, high speed, and low power consumption for efficient and reliable performance.` Source: `https://manuals.plus/asin/B0DL5MM5BH`
- a mirrored KK3 Max page states: `At its heart, the controller is powered by a custom GuliKit GP3F128 chip, ensuring efficient processing and reliable performance across various platforms.` Source: `https://manuals.plus/video/c45a6fd180e9ff17b3f22ddb319681f99ba940fe3f9c4a75a3758824d0d11b89`
- a GuliKit X post for the KK3 line claims a `Gpower CPU` with `1000Hz polling rate for wired connection`

That changes the hardware picture materially. The MCU family is no longer completely unknown. The strongest current model is that TT MAX and KK3-family controllers share a GuliKit custom `Gpower` CPU family centered on `GP3F128`, with the TT update blob acting as a wrapped container for that platform. What is still missing is the architecture, flash mapping, bootloader layout, and the commit path that consumes the copied `.bin`.

## Browser-tooling findings

I also pulled apart GuliKit's official web tooling to check whether there is any hidden native paddle path exposed there.

What I confirmed:

- The public Setup Tool does **not** support TT MAX. Its model table resolves to `Elves 2 Pro`, `Elves 2`, `KK3 Max`, `KK3 Pro`, and `KK2 T`.
- The setup code has four separate rear-button fields internally:
  - `assistantLeft1`
  - `assistantLeft2`
  - `assistantRight1`
  - `assistantRight2`
- The user-facing labels for those fields still only map `G1` to `G4` onto ordinary buttons like `A`, `B`, `X`, `Y`, d-pad directions, `L3`, `R3`, `L`, `R`, `ZL`, `ZR`, `ADD`, and `SUB`.

That means I did **not** find a dormant web-exposed `P1` to `P4` mode hiding behind obfuscated UI strings.

One non-obvious protocol detail did come out of that work:

- The supported-model Setup Tool is not using WebHID for ordinary settings writes.
- It sends encoded configuration commands through the Gamepad API `vibrationActuator.playEffect()` path.
- The calibration tool does use WebHID, but the setup flow and the calibration flow are separate channels.

That is a real reverse-engineering result, but it does not unlock a TT MAX native paddle patch by itself because TT MAX is not one of the setup-tool-supported models and the exposed rear-button command set still maps only to existing controls.

## Live hardware findings

I now have read-only USB observations from a real TT MAX on a Windows 10 host.

### Normal mode

The earlier `VID_3554&PID_F508` attribution is no longer trustworthy.

What changed:

- I built a Windows-side HID probe and ran it live on the remote host.
- The currently attached `VID_3554&PID_F508` device identifies itself through `hidapi` as:
  - manufacturer: `pulsar`
  - product: `X2H Mini`
- Its live interface map is:
  - `MI_00`: keyboard
  - `MI_01&Col03`: consumer control
  - `MI_01&Col04`: system control
  - `MI_01&Col01`, `Col02`, `Col05`, `Col06`: vendor-defined collections on usage pages `FF05`, `FF03`, `FF02`, and `FF04`
  - `MI_02`: mouse

That means the cached `F508` composite-HID evidence from the Windows host is **confounded by another OEM device** and cannot currently be used as proof of TT MAX normal-mode behavior.

I am therefore withdrawing the earlier claim that TT MAX normal mode is confirmed as `3554:F508`.

What remains true:

- `0x3554` is still a real OEM USB vendor ID used by Shenzhen Jiangmeng hardware.
- The host has stale `3554:F506`, `3554:F507`, and `3554:F508` registry entries.
- Those stale `F506`, `F507`, and `F508` caches all share the same keyboard + vendor collections + consumer/system + mouse composite layout, so they are not a reliable TT-specific discriminator by themselves.
- Until I capture TT MAX normal mode live in isolation, I cannot call any runtime identity fully confirmed.

I also checked the larger `artifacts/usbpcap3-readtest.pcapng` capture so it would not silently contaminate the TT evidence pool.

What that file actually shows at the start:

- a Realtek hub descriptor: `0BDA:5411`
- a separate HID composite descriptor with `VID:PID FEED:0001`
- no mass-storage SCSI traffic at all

That means `usbpcap3-readtest.pcapng` is **not** a clean TT MAX update capture and is not yet trustworthy as TT MAX normal-mode evidence either.

I also used the Windows PnP property store to tighten the stale `3554:*` conclusion:

- `USB\\VID_3554&PID_F507\\...` reports `DEVPKEY_Device_BusReportedDeviceDesc = X2H Mini`
- `USB\\VID_3554&PID_F508\\...` also reports `DEVPKEY_Device_BusReportedDeviceDesc = X2H Mini`
- even the older cached `USB\\VID_3554&PID_F506\\...` reports `DEVPKEY_Device_BusReportedDeviceDesc = VGN F1 MOBA`

So the Windows cache now independently confirms that the `3554:F507` and `3554:F508` candidates belong to the Pulsar / VGN mouse family, not TT MAX.

I now also have a much stronger candidate for TT MAX normal mode on this host:

- `USB\\VID_057E&PID_2009\\000000000001`
- same physical location string: `Port_#0007.Hub_#0001`
- `DEVPKEY_Device_BusReportedDeviceDesc = Pro Controller`
- `DEVPKEY_Device_LastArrivalDate = 2026-04-21 23:18:25` local host time
- `DEVPKEY_Device_LastRemovalDate = 2026-04-21 23:32:20` local host time

There is also a second cached `057E:2009` instance on the same port:

- `USB\\VID_057E&PID_2009\\6&3365FBAF&0&7`
- last arrival `2026-04-21 23:00:23`
- last removal `2026-04-21 23:00:30`

That does **not** prove the TT MAX always uses `057E:2009`. It does strongly suggest that, on this Windows host, TT MAX normal mode has at least one runtime identity compatible with Nintendo's standard `Pro Controller` USB profile. This matches the user's observed behavior that the controller was being read as `Pro Controller` instead of a GuliKit-specific name.

I now also have a second same-port normal-mode identity from the cached Windows registry:

- `USB\\VID_045E&PID_028E\\000001`
- device description: `Xbox 360 Controller for Windows`
- location: `Port_#0007.Hub_#0001`

That means the same physical port has now hosted all three of these identities:

- `045E:028E` - XInput-style `Xbox 360 Controller for Windows`
- `057E:2009` - Switch-style `Pro Controller`
- `34D3:1100` - the update-mode `Gulikit X` mass-storage stub

This is still not a live descriptor capture, so I am not calling the full mode matrix fully proven yet. It is now the strongest host-side model:

1. a PC XInput personality
2. a Switch / Pro Controller personality
3. a separate updater personality

The official manual now reinforces that interpretation:

- `Mode Button: Double-click to switch modes`
- `Set the controller to PC mode` for wired or Bluetooth PC pairing
- `Set the controller to NS mode` for Switch / Switch 2 pairing
- Bluetooth pairing in PC mode advertises `GuliKit XW Controller`

For the native `P1` to `P4` goal, that model has one important implication:

- XInput is structurally hostile to extra native buttons
- the Switch / HID personality is the more plausible place for distinct rear-paddle bits or a vendor-defined extension
- if the firmware only exposes stock XInput and stock Pro Controller layouts, the native patch will need descriptor and report changes, not just a simple remap-table change

### Update mode

With the controller powered off, then started while holding `APG + Home`, Windows enumerates a different device:

- `USB\\VID_34D3&PID_1100&REV_0100`
- class: `USB Mass Storage`
- bus-reported description: `GULI  Disk`

Windows mounts a removable FAT volume:

- label: `GuliKit`
- drive letter: `E:`
- size: `134152192` bytes

The root contains exactly one vendor file:

- `GULI.TXT`

Its full contents are:

```text
www.gulikit.com 
version 6.0
```

That version marker is significant. The live controller had newer TT application firmware available, but the update-mode storage stub still reports `version 6.0`. The simplest explanation is that this removable-drive environment is a separate updater or bootloader component, not the main gameplay firmware image itself.

Windows PnP properties add one more concrete identity clue for the same instance:

- instance id: `USB\\VID_34D3&PID_1100\\6&3365FBAF&0&7`
- `DEVPKEY_Device_BusReportedDeviceDesc = Gulikit X`
- `DEVPKEY_Device_InstallDate = 2026-04-21 21:53:44` local host time
- `DEVPKEY_Device_LastArrivalDate = 2026-04-21 23:37:46` local host time
- `DEVPKEY_Device_LastRemovalDate = 2026-04-21 23:46:59` local host time

That strengthens two points:

- the update-mode device is vendor-branded at the PnP layer as `Gulikit X`, not just as a generic storage device
- the updater stub and one of the `057E:2009` `Pro Controller` instances share the same physical port string `Port_#0007.Hub_#0001`, which is the strongest current host-side link between TT MAX update mode and TT MAX normal mode
- the saved USBPcap trace at about `2026-04-21 20:57 UTC` corresponds to an earlier session than the registry's most recent arrival/removal timestamps, so I still cannot use those registry timestamps to infer the disconnect timing for the exact captured trace

There is also now a documentation conflict around how update mode is entered:

- the official V6.8 firmware page says `APG + Home`
- the AKNES NS69 FAQ says `APG + A`
- a Scribd mirror of GuliKit's upgrade guide also says `APG + A`

The live Windows session that produced the confirmed `34D3:1100` stub was already achieved, so update mode itself is real. What remains unresolved is whether:

1. the combo changed between revisions
2. one guide is wrong
3. different runtime modes accept different entry combos

That conflict matters because it is exactly the kind of hidden boot-mode detail that may matter if a future RE path needs a more privileged updater personality.

### Captured write-transaction findings

I now have a parsed USBPcap trace for an official V6.8 update copy.

What it proves:

- Windows talks to the controller in update mode as a plain FAT16 mass-storage volume.
- The captured copy performs exactly `17` host-side `WRITE(10)` requests.
- Those writes only touch:
  - LBA `0` - boot sector
  - LBA `1` and `33` - the two FAT copies
  - LBA `65` - root directory sectors
  - LBA `225` - firmware file data
- The parsed boot sector is stable and normal:
  - OEM name: `MSDOS5.0`
  - bytes/sector: `512`
  - sectors/cluster: `32`
  - FAT count: `2`
  - sectors/FAT: `32`
  - root directory start: LBA `65`
  - data region start: LBA `97`
  - total sectors: `262144`
  - volume label: `GuliKit`
  - filesystem type: `FAT16`
- The final root directory contains:
  - `GULI.TXT`
  - `System Volume Information`
  - `NS69_TT-MAX_V6.8.bin`
- The firmware file entry is:
  - short name: `NS69_T~1.BIN`
  - start cluster: `6`
  - cluster chain: `6 -> 7 -> 8`
  - file size: `45920`
- That cluster chain maps back to data LBA `225`, which is exactly where the large `WRITE(10)` occurs.
- The `LBA 225` write payload matches the official `firmware/NS69_TT-MAX_V6.8.bin` byte-for-byte for the first `45920` bytes, followed by `160` zero bytes of last-sector slack.
- After that large data write, there are **no more writes to the firmware data region** in the trace. The remaining writes only touch FAT, root-directory, and boot-sector metadata.

One subtle but useful detail came out of the repeated metadata writes:

- the final boot-sector delta is a single byte flip at offset `37`, from `0x01` to `0x00`
- the FAT-sector delta flips byte `3` from `0x7f` to `0xff`

Those look like normal FAT dirty/clean bookkeeping, not host-side firmware wrapping or device-specific secret commands.

### Captured command-sequence findings

I extended the capture parser so it now summarizes the full SCSI command sequence instead of only the `WRITE(10)` payloads.

For `artifacts/ttmax-v68-update-usbpcap1.pcapng`, the host-side command mix is:

- `17` x `Write(10)`
- `6` x `Test Unit Ready`
- `4` x `Prevent/Allow Medium Removal`
- `4` x `Request Sense`

What matters:

- there are **no** vendor-specific SCSI commands in the captured copy window
- there is **no** `Start Stop Unit`, explicit eject, or other obvious host-side "commit now" command
- every `Prevent/Allow Medium Removal` attempt fails with `Check Condition`
- the follow-up `Request Sense` replies decode to:
  - sense key: `Illegal Request`
  - ASC/ASCQ: `Invalid Command Operation Code (0x20/0x00)`

That strongly suggests the updater stub is a deliberately thin fake-disk implementation. Windows is just writing a normal FAT file and occasionally probing optional MSC commands that the device does not implement. If the firmware image is later consumed, that commit step is most likely autonomous on the device side after the file lands on disk, not something explicitly triggered by a host-side vendor command in this trace.

One caution remains:

- this capture ends after another successful `Test Unit Ready` at about `6.07` seconds from the start of the trace
- the device disconnect / auto-power-off is **not** present in this capture window

So this trace narrows the commit-path theory, but it still does not capture the actual moment where the controller consumes the copied `.bin`.

## Hard blocker

I do **not** have enough evidence yet to derive a real native-paddle firmware patch safely.

The blocker is not “I did not try.” The blocker is:

- the update blobs are opaque
- even three adjacent TT revisions still behave like fresh full-container rewrites
- the only TT-specific USB identity that is currently confirmed is the bootloader-style mass-storage facade
- the earlier `3554:F508` normal-mode lead is contaminated by a non-TT device on the same Windows host
- the captured write transaction only proves plain FAT file copy semantics on the host side; it still does **not** reveal how the bootloader validates or commits the copied `.bin`
- teardown now confirms a central `GP3F128` package, but there is still no flash mapping, bootloader dump, or decoded container format

Without at least one of these extra lanes:

- a captured post-copy commit / reboot session that shows what the device does after the file lands on disk
- a bootloader or application flash dump from the `GP3F128` platform
- a confirmed TT MAX normal-mode USB capture with other confounding `3554:*` devices excluded

I would just be inventing a patch format, not reverse engineering one.

## FCC and commercial-document findings

I now have one more solid product-identity anchor from external records:

- FCC ID: `2BLVF-NS69`
- product name: `TT MAX Controller`
- equipment class: `DTS - Digital Transmission System`
- grant date: `2025-12-08`
- frequency range: `2402 MHz` to `2480 MHz`
- listed public filing buckets: attestation statements, cover letters, label/location info, RF exposure info, antenna specification, BLE report, and test setup photos

What I **did not** get from the public filing mirrors:

- no public internal board photos
- no GP3F128 details
- no USB VID/PID details
- no updater or bootloader description

So the FCC lane is useful for confirming the regulatory identity of `NS69`, but it did not unlock the native patch path.

I also now have a vendor-adjacent hardware note from AKNES's NS69 FAQ:

- AKNES says its `Revision` hardware specifically addressed rear-button issues found during pre-release testing

That lines up with community reports about rear-button tactility problems and with the V6.8 firmware note about APG and rear-button interaction bugs. It does **not** prove a firmware-only root cause, but it is a strong warning that some rear-button behavior on TT MAX has had both hardware and firmware churn very early in the product life.

## New artifact-recovery helpers

I added two helpers to reduce the manual friction around future firmware recovery:

### 1. Captcha OCR helper

`tools/ocr-gulikit-captcha.py`

This enlarges and crops GuliKit's captcha images, saves per-digit crops, and performs a best-effort `tesseract` pass on each digit. It is not perfect, but it is much better than repeatedly guessing raw 4-digit images by eye.

Example:

```bash
uv run python tools/ocr-gulikit-captcha.py /tmp/tt-scan-captcha.gif
```

### 2. File ID range scanner

`tools/scan-gulikit-file-ids.py`

This probes a narrow `filedownload` ID range from a saved captcha session. Observed behavior suggests a **successful verification consumes the captcha token**, so each run is best-effort and usually yields at most one success. That is still enough to hunt adjacent firmware packages in small ID windows.

Example:

```bash
uv run python tools/scan-gulikit-file-ids.py /tmp/tt-scan-state.json --captcha-code 3450 --start 2993190 --end 2993245
```

Observed behavior from live testing:

- wrong captcha reads fail cleanly with `Verification code is wrong！`
- a correct captcha yields a signed download URL
- successful use appears to burn the captcha token
- racing multiple candidate IDs in parallel can surface one valid signed URL from a range

## What is implemented now

### 1. Official firmware downloader

`tools/download-gulikit-file.py`

This gets a real signed download URL from GuliKit's captcha-gated `filedownload/<id>` flow and can save the official zip locally.

It now also supports `--reuse-state`, which lets me submit a captcha code against the exact saved session and image instead of accidentally regenerating a fresh captcha during a retry.

### 2. Firmware analysis tool

`tools/analyze-ttmax-firmware.py`

This fingerprints a firmware blob and compares two images so future work can be based on repeatable facts instead of ad hoc shell output.

### 3. Re-application patcher

`tools/apply-firmware-patch.py`

This is the durable “wire it back in after an update” mechanism.

Once actual native-paddle patch offsets are known, the workflow is:

1. download the new official firmware
2. verify its hash
3. apply the manifest
4. flash the patched `.bin`

The patcher already supports:

- input hash verification
- byte-precondition verification at each patch site
- deterministic in-place replacement
- signature-based patch anchoring with `find_hex`
- wildcard search bytes such as `??` in `find_hex`
- relative patch placement with `offset_adjust`
- match-count verification so a supposedly stable patch anchor does not silently hit the wrong region

### 4. Windows HID / registry probe

`tools/ttmax-hid-probe.py`

This is the new low-risk probe tool for the next live hardware session.

It supports:

- `cache`: dump cached Windows `Enum\\USB` and `Enum\\HID` metadata for a chosen `VID:PID`
- `enumerate`: list live hidapi-visible interfaces with usage pages, usages, interface numbers, and raw paths
- `get-feature`, `read`, `send-feature`, and `send-output` for targeted probing once the correct live TT MAX interface is isolated

Its current main value is that it let me prove the `3554:F508` confound instead of continuing to treat that device as TT MAX.

### 5. USB mass-storage write extractor

`tools/extract-usbms-writes.py`

This parses a USBPcap trace of the update volume and reconstructs the host-side `WRITE(10)` transaction as concrete artifacts.

It currently supports:

- enumerating every `WRITE(10)` request with request frame, data frame, status frame, LBA, sector count, and payload hash
- extracting the raw sector payloads into standalone `.bin` files
- reconstructing a sparse final FAT image from the captured writes
- parsing the FAT16 boot sector and root directory
- tracing FAT cluster chains for written files
- matching a recovered on-disk file entry or payload back to an official firmware `.bin`
- summarizing the full SCSI command sequence, including `Test Unit Ready`, `Prevent/Allow Medium Removal`, `Request Sense`, command-status results, and decoded sense responses

Its main value is that it turns the updater path into something repeatable and testable instead of ad hoc tshark commands.

## What still has to happen for a true native patch

1. Recover either an even older TT revision, a bootloader image, or a live update-session capture that reveals the inner container semantics.
2. Capture USB descriptors and traffic in TT update mode and in a **confirmed isolated TT MAX normal mode** session.
3. Identify whether the blob is encrypted, compressed, or authenticated.
4. Extract or recover the actual code image.
5. Locate HID report descriptors, report packing, and rear-button dispatch.
6. Patch the image to emit distinct native rear-paddle buttons.
7. Regenerate a valid update container.
8. Flash and validate on hardware.

## Next useful move

The highest-value next move is a captured **post-copy** update session that goes past the plain FAT write phase:

- a USBPcap trace covering:
  - entry into update mode
  - the file copy of an official TT firmware image
  - safe eject if the vendor flow expects it
  - the device disconnect / reconnect behavior after the copy
  - any follow-up enumeration that happens when the controller actually consumes the `.bin`
- a raw image of the exposed FAT volume before and after the firmware file is copied
- if possible, descriptor capture for both:
  - confirmed TT MAX normal mode, captured with other `3554:*` OEM peripherals unplugged or positively excluded
  - update mode `34D3:1100`

I now have the host-side file-copy transaction. The missing piece is the device-side commit path after that copy, plus the confirmed normal-mode USB identity.
