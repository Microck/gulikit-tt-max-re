# GuliKit TT MAX Reverse Engineering Notes

Half-baked but real research and tooling for reverse engineering the GuliKit TT MAX (`NS69`) controller, with a focus on native rear-paddle support and firmware/update behavior.

Current status:

- native `P1` to `P4` paddle patch is **not solved**
- TT MAX appears to expose multiple personalities on Windows:
  - `045E:028E` (`Xbox 360 Controller for Windows`)
  - `057E:2009` (`Pro Controller`)
  - `34D3:1100` (update-mode mass-storage stub)
- the official TT firmware blobs still look like opaque wrapped containers, not plain flash images

What is here:

- research notes:
  - `ttmax-native-firmware.md`
  - `ttmax-findings.md`
  - `ttmax-apg-format.md`
- tooling:
  - firmware diffing and patch helpers
  - GuliKit download helpers
  - USB mass-storage trace extraction
  - Windows HID / registry probing
- selected artifacts used by the notes

What is not here:

- a working native firmware patch
- any claim that the controller already exposes true native `P1` to `P4`
- a guaranteed safe flashing workflow for modified TT firmware

If you have live captures, board photos, or older TT firmware packages, those are the highest-value next inputs.
