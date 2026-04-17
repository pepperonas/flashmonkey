# Research Status

Empirical record of what works, what fails, and where the investigation currently sits.
Only entries that were actually tested are kept here.

## Primary goal

Remove the 22 km/h speed limit on the Navee ST3 Pro DE (PID 23452). The limit is enforced
inside the BLDC motor-controller firmware (region byte `0xCF` at offset `0x0011`).
`0xCF` = DE (22 km/h), `0xB7` = Global (30 km/h).

## What works (verified)

| Capability | Evidence |
|---|---|
| BLE pairing + auth (5 AES keys) | `ota_flasher.py --read-info` reads version/SN/settings every session |
| Reading BLDC/meter/BMS firmware versions via CMD `0x73` | Tested dozens of sessions |
| Sending speed commands `0x6E` and `0x6B` | ACKs received, but controller still caps at 22 km/h (commits `ab1c622`, `cd532c9`) |
| **Meter OTA with stock FW** | 1080/1080 blocks ACKed, `rsq dfu_ok` returned — confirmed 2026-04-16 |
| SPI-flash direct read/write via rtltool | Commit `e4178ec`: full 512 KB dump + sector write round-trip verified |
| BLDC header CRC algorithm | CRC-16/XMODEM over body from first non-0xFF byte, BE @ offset 0x13-0x14 — verified on 26 of 32 BLDC firmware files (`tools/header_crc_search.py`) |
| SHA-256 recomputation after meter FW patch | Algorithm in `tools/patch_firmware.py` produces hash that matches original FW exactly |
| Ghidra headless analysis of dashboard FW | PyGhidra pipeline in `tools/ghidra_se_analyze.py` — auto-analysis + decompiler |

## What fails (verified)

| Attempt | Symptom | Sessions tested |
|---|---|---|
| BLDC OTA via BLE (type = 0x02 header) | NAK `15 01` on block 1, 0 ACKs | 36+ sessions, all with the same outcome (see `tools/ota_flash_log.json`) |
| Patched meter OTA (SHA-256 correct) | All blocks ACKed, then silence — no `rsq dfu_ok` and no `rsq dfu_error` after EOT | 2026-04-16 test with `navee_meter_v2.0.3.1_PATCHED_OTA.bin` |
| UART MitM on Yellow wire | Controller ignores manipulated speed-limit byte | Commits `ab1c622`, `cd532c9` (1168 frames injected) |
| Dashboard replacement | New dashboard → same 22 km/h cap | Vector 11/12 |
| `dfu_start 2` dispatch inside dashboard FW | String `"down dfu_start 2"` is NOT in the dashboard binary — falls through to silent_dfu (which writes to the dashboard's own flash, not BLDC) | String scan of `navee_full_flash_dump.bin` |
| UART sniff during BLDC-OTA attempt | 0 XMODEM bytes flow from dashboard to controller on any wire | `docs/BLDC_DFU_ANALYSIS.md` (archived in git history) |

## Architecture findings

### Dashboard contains Apple Find My Network (FMNA) code
`fmna_*` (33 symbols), `fm_crypto_*` (5 symbols), `ServerSharedSecret`, `PairingSession`,
`SerialNumberProtection`, `secp256r1`, `AES-256-GCM`, `SHA256` — all present in Bank A.
Apple's FMNA certification requires a hardware Secure Element. The SE is likely on the
dashboard PCB but not yet physically identified. See `docs/SECURE_ELEMENT.md`.

### Boot-time validator (Ghidra `FUN_0080d400`)
For the app image (image_id `0x2793`), the boot validator runs exactly one check:
`func_0x00601b9c` which validates SHA-256. The "loading check" (`func_0x005f5dea`) is
gated by header bit 2 which is `0` for the app image, so it is skipped. **Patches
delivered via SPI-direct should boot correctly if SHA-256 is recomputed.**

### OTA-time validator (not yet located)
After all XMODEM blocks are transferred, the dashboard invokes `func_0x0000C880(0x2793)`
which lives **outside the app image** — likely in the PATCH image at file offset
`0x003000-0x00CFFF` (present in the dump but not yet analyzed) or in the BootROM (not
dumped). This validator silently rejects any modification even with a correct SHA-256.

### `down dfu_start 3` has dedicated handler, but not 1/2/4
String scan confirms only `"down dfu_start"` (default → silent_dfu) and
`"down dfu_start 3"` (BMS-specific relay) exist as literal strings in the dashboard FW.
`dfu_start 1/2/4` all fall through to the silent_dfu handler, which only writes to the
dashboard's own flash. There is no code path in this FW version that relays XMODEM
blocks to the BLDC controller.

## Open questions

1. **Does the SE periodically re-validate app-code integrity?**
   - Hypothesis: no — Apple FMNA uses the SE for identity attestation, not code integrity.
   - Test: flash a known-good SPI-direct patch, use the scooter for several days, verify
     patch still present via read-back.

2. **What does `func_0x0000C880` do?**
   - Load the PATCH image (`tools/firmware/navee_full_flash_dump.bin` offset `0x003000-0x00CFFF`)
     into a separate Ghidra project at base `0x00803000` and decompile.

3. ~~**Can the LKS32MC081 be put into ROM bootloader mode via UART on the ESC board?**~~
   - **Answered: No** — the LKS32MC08x datasheet (v1.93, now in `docs/`) describes
     no UART ISP bootloader. Flash programming is exclusively via SWD. UART probing
     of TX0/RX0 or TX2/RX2 pads for bootloader entry would therefore fail.
   - Replacement question: **Can we reach SWD (pins 47/48) + RSTN (pin 2) on the
     PCB?** RoboCoffee did it on the same chip on Xiaomi 3 Lite (same OEM Brightway)
     without protection bypass — factory left the two soft protections unused.

## Remaining attack paths (realistic)

| Path | Cost | Prerequisite | Estimated effort |
|---|---|---|---|
| **SPI-direct patch delivery** | 0 € | Arduino + CP2102 (already available) | ~2 h once a patch is designed |
| **Decompile PATCH image** → understand OTA 2nd validator | 0 € | Ghidra (installed) | 4–10 h |
| **LKS32MC081 SWD via ST-Link v2** | ~10 € ST-Link clone | Find SWD pads on ESC PCB (pins 47/48) | ~2-4 h hardware setup. Datasheet confirms no hardware RDP; RoboCoffee succeeded on same chip. |
| **Physical BLDC controller swap** | ~30 € AliExpress | Soldering access to ESC PCB | ~2 h mechanical work |

## Tools in this repo (only the relevant ones)

| Tool | Status | Notes |
|---|---|---|
| `tools/ota_flasher.py` | Works for meter FW; instrumented with JSON logging | `tools/ota_flash_log.json` holds 100+ sessions |
| `tools/flash_meter.py` | Thin wrapper around `ota_flasher.py` — flashes stock or custom meter FW | Verified with ORIGINAL |
| `tools/flash_de_stock.py` | Same wrapper for BLDC FW; **verifies BLDC OTA cannot succeed** | Keep as negative-test reference |
| `tools/patch_firmware.py` | Meter-FW speed patch + SHA-256 recompute | SHA-256 algorithm is correct; OTA-delivery still blocked by 2nd check |
| `tools/patch_bldc_region.py` | BLDC region byte + CRC-16/XMODEM recompute | Correct CRC, but no delivery path |
| `tools/header_crc_search.py` | Identified the BLDC CRC algorithm empirically | Result: CRC-16/XMODEM over code body |
| `tools/se_scan.py` | Static FW scan for Secure Element indicators | Found Apple FMNA stack |
| `tools/ghidra_se_analyze.py` | PyGhidra automation: find functions by string XRef + decompile | Requires `GHIDRA_INSTALL_DIR` env var |
| `tools/sigrok_decoders/i2c_se/` | Protocol decoder for PulseView | Not yet used (no logic analyzer captures yet) |
| `tools/uart_direct_flasher.py` | Placeholder for LKS32MC081 ISP — detection mode works | Flash path not yet verified |

## Commit references for claims

- `1b0889d` — Meter OTA verified 1080/1080 blocks
- `e4178ec` — SPI flash dump + patch write verified via rtltool
- `e24f021` — SHA-256 algorithm reverse-engineered
- `8099a7c` — Second validator blocks modified FW with correct SHA-256
- `f28d5a7` — BLDC OTA investigation concluded: dashboard does not relay
- `39da04c` — UART sniffer confirmed no XMODEM traffic during BLDC DFU
- `ab1c622` — Controller ignores speed bytes injected via Yellow wire
- `cd532c9` — Yellow wire protocol decoded (0x51/0xAE frames, speed byte @ offset 10)
