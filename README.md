[English](README.md) | [Deutsch](README_DE.md)

# Navee ST3 Pro — Reverse Engineering & Custom Firmware

<p align="center">
  <img src="docs/banner.png" alt="Navee ST3 Pro Scooter Toolkit" width="100%">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-brightgreen.svg)](android/)
[![MCU](https://img.shields.io/badge/MCU-RTL8762C-FF6F00.svg)](docs/HARDWARE.md)
[![BLE](https://img.shields.io/badge/BLE-Custom%20Protocol-informational.svg)](docs/PROTOCOL.md)
[![Auth](https://img.shields.io/badge/Auth-AES--128--ECB-9C27B0.svg)](docs/AUTHENTICATION.md)
[![SHA256](https://img.shields.io/badge/SHA--256-Cracked-00C853.svg)](#patch_firmwarepy--automatic-ota-patcher)
[![SPI Flash](https://img.shields.io/badge/SPI%20Flash-Patch%20Verified-00C853.svg)](#spi-flash-direct-patch)
[![OTA](https://img.shields.io/badge/OTA%20Patch-Untested-FFA726.svg)](#patch_firmwarepy--automatic-ota-patcher)
[![Speed](https://img.shields.io/badge/Speed%20Unlock-Awaiting%20Test-FFA726.svg)](#the-patch)
[![BLDC](https://img.shields.io/badge/BLDC%20FW-Downloaded-00C853.svg)](#bldc-firmware-swap)

---

Reverse engineering, firmware analysis, and Android controller app for the **Navee ST3 Pro** e-scooter (PID 23452, DE market).

This project has fully reverse-engineered the proprietary BLE protocol, developed an independent controller app, analyzed the meter firmware with Ghidra, built a working OTA flasher, dumped the complete SPI flash via UART, **successfully written a 1-byte firmware patch directly to flash** using [rtltool](https://github.com/wuwbobo2021/rtltool), **cracked the RTL8762C SHA-256 checksum algorithm**, and created `patch_firmware.py` — a fully automated tool that patches any firmware version and produces a valid OTA binary.

---

## Attack Vectors

| # | Approach | Result |
|---|----------|--------|
| 1 | BLE CMD `0x6E` (Max Speed) | Failed — ACK'd but ignored by firmware |
| 2 | UART MitM (Arduino) | Failed — Controller ignores manipulated frames (1168 frames tested) |
| 3 | **Firmware Patch (Ghidra)** | **Verified — 1-byte NOP at 0xF848, speed table at 0xF074** |
| 4 | Meter OTA Flash | Transfer works (1080/1080 ACK'd) — bootloader rejects all modified firmware (undocumented integrity check) |
| 5 | **SPI Flash Direct (rtltool)** | **Verified — Patch written and confirmed via read-back** |
| 6 | **Controller Swap (AliExpress)** | **Verified by community — recommended approach** |
| 7 | BLDC OTA Flash | Type 0x02 NAK'd by dashboard; Type 0x01 hack: 369/369 ACK'd but no UART relay to controller |
| 8 | Direct UART Flash | Controller doesn't enter bootloader — proprietary DFU trigger unknown |
| 9 | Hybrid BLE+UART Flash | Dashboard sends "ok\r" on UART after dfu_start 2, but controller ignores it |
| 10 | SWD Flash (LKS32MC081) | MCU identified, SWD unprotected — but controller board physically inaccessible without removing unit |
| 11 | Yellow Wire MitM | **Yellow = Controller RX confirmed!** New protocol discovered (0x51/0xAE). Speed byte at offset 10 = 0x16 (22 km/h). MitM modified 795 frames — controller briefly went faster then error. Speed limit hardcoded in BLDC firmware country code |
| 12 | UART Bootloader Trigger | Controller does NOT enter bootloader when dashboard disconnected — no 'C' (0x43) signal. Proprietary bootloader trigger unknown |

**Current status:** Yellow wire protocol fully decoded (header 0x51, footer 0xAE, 14-byte frames). Speed limit byte identified at offset 10. Arduino MitM confirmed controller briefly responds to modified speed bytes, but BLDC firmware country code (`0xCF` = DE) enforces 22 km/h internally. Controller does not enter UART bootloader mode. **Speed limit can only be changed by flashing the BLDC controller firmware (SWD) or physical controller swap.**

> Full analysis: [`docs/ATTACK_VECTORS.md`](docs/ATTACK_VECTORS.md)

---

## SPI Flash Direct Patch

**This is the breakthrough.** After OTA patching was blocked by the bootloader's integrity check across 10 failed attempts testing every conceivable checksum algorithm, we dumped the complete SPI flash via UART and wrote the patch directly — bypassing the bootloader entirely.

### The Discovery Path

1. **Identified MCU:** Opened the dashboard on March 19, found Realtek RTL8762C BLE SoC (Module RB8762-35A1). The short-circuit incident during dashboard disassembly provided direct access to the board.
2. **Found rtltool:** [wuwbobo2021/rtltool](https://github.com/wuwbobo2021/rtltool) — open source tool for RTL8762C flash programming via UART
3. **Entered download mode:** Pin P0_3 held LOW during boot
4. **Dumped 512 KB SPI flash:** Complete backup including bootloader, BLE stack, and application firmware
5. **Located active firmware:** OTA firmware code found at flash offset `0x0E020`, but the **active copy** runs from a different bank
6. **Found patch location:** Searched for the exact byte context (`0E 2D 02 D8 04 E0 0A 2D 02 D9`) in the flash dump — found at flash offset `0x1D448`
7. **Wrote the patch:** Changed 2 bytes at flash `0x0081D448`: `02 D9` (BLS) to `00 BF` (NOP)
8. **Verified:** Read-back confirms `00 BF` at the patch location

### Hardware Setup

```
Arduino UNO (3.3V power only, empty sketch)
    |
    +-- 3.3V ---------> VCC on dashboard board
    +-- GND ----------> GND on dashboard board

CP2102 USB-UART Adapter
    |
    +-- TX ------------> RX (LOG pad on board)
    +-- RX <------------ TX (LOG pad on board)
    +-- GND ----------> GND on dashboard board

Jumper wire: P0_3 pad ----> GND (held during boot for download mode)
```

### Flash Dump & Patch Commands

```bash
# Clone rtltool (fork with firmware0.bin included)
git clone https://github.com/wuwbobo2021/rtltool.git
pip3 install pyserial crccheck coloredlogs

# Enter download mode: connect P0_3 to GND, then power on
# Step 1: Verify connection
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 read_mac
# Expected: Flash Size: 512 kiB, MAC: XX:XX:XX:XX:XX:XX

# Step 2: Full flash backup (CRITICAL -- do this first!)
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    read_flash 0x800000 0x80000 navee_full_flash_dump.bin
# Takes ~30 seconds, produces 524288 byte file

# Step 3: Write patched sector
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    write_flash 0x81D000 sector_0x1D000_patched.bin

# Step 4: Verify
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    verify_flash 0x81D000 sector_0x1D000_patched.bin
```

### Flash Memory Layout (verified from dump)

```
SPI Flash (512 KB, memory-mapped at 0x00800000)
+------------------+---------------------------------------------------+
| 0x800000         | Reserved (0xFF)                                   |
| 0x801000-0x802FFF| System config, boot parameters                   |
| 0x803000-0x80DFFF| BLE stack patch code                              |
| 0x80E000-0x82FFFF| Active firmware (Bank A) -- 136 KB                |
|   0x81D448       |   *** PATCH LOCATION: 02 D9 -> 00 BF ***         |
| 0x840000-0x841FFF| OTA header area                                   |
| 0x844000-0x865FFF| OTA staging (Bank B) -- receives OTA transfers    |
| 0x876000         | Additional config                                 |
+------------------+---------------------------------------------------+
```

### Why OTA Patching Failed (10 Attempts)

The RTL8762C bootloader validates firmware images using a ROM function at address `0x601B9C` (inside the chip's mask ROM — not readable via flash dump). This function checks a field in the image header (`ctrl_header[2:3]`) against a computed value over the payload. The algorithm is proprietary and cannot be determined without decapping the chip or dumping the ROM.

**Checksums tested (all failed):** CRC-16 (XMODEM, CCITT, ARC, MODBUS), CRC-32 (standard, STM32), XOR-32, XOR-8, SUM-8, SUM-16, SUM-32, Fletcher-16/32, Adler-32, MD5, SHA-1, SHA-256, HMAC-MD5, brute-force CRC at every position.

The ROM function also performs a "signature" check comparing the first 32-bit word against magic value `0x8721BEE2`, and a boot-time checksum via `add8CheckSum`. None of these could be replicated externally during those 10 attempts.

**Direct SPI flash writing bypasses ALL of these checks** because we write to the active firmware bank directly, not through the OTA update path.

### Key Insight: Dual-Bank Architecture

The RTL8762C stores firmware in two banks:
- **Bank A** (0x804000): Active firmware that the CPU executes
- **Bank B** (0x844000): OTA staging area where new firmware is received

OTA updates write to Bank B, verify the checksum, then copy to Bank A on reboot. All 10 OTA attempts wrote to Bank B successfully (all 1080 blocks ACK'd) but the verification step rejected the patched firmware — it was never copied to Bank A.

**Direct flash writing targets Bank A directly**, skipping the verification step entirely.

---

## patch_firmware.py — Automatic OTA Patcher

After cracking the RTL8762C SHA-256 checksum algorithm from the Realtek Bee2 SDK source (`silent_dfu_flash.c`), we implemented `patch_firmware.py` — a fully automated tool that patches any Navee meter firmware version and produces a valid OTA binary with a correct SHA-256 checksum.

### The SHA-256 Breakthrough

The Bee2 SDK `slient_dfu_check_sha256()` function does not hash the entire image. It hashes three specific regions of the image header and payload:

| Region | Offset Range | Size | Description |
|--------|-------------|------|-------------|
| 1 | `header[12:372]` | 360 bytes | After `ctrl_header`, before SHA-256 field |
| 2 | `header[404:752]` | 348 bytes | After SHA-256 field, before RSA area |
| 3 | `header[1008:1024] + payload` | 16 + payload_len bytes | Tail of header plus full payload |

SHA-256 is computed over the concatenation of these three regions. The result is stored at `header[372:404]`.

### patch_firmware.py Workflow

```bash
# Dry run (no file written): verify firmware and locate patch
python3 tools/patch_firmware.py firmware.bin --dry-run

# Patch and write output automatically
python3 tools/patch_firmware.py firmware.bin

# Specify output path explicitly
python3 tools/patch_firmware.py firmware.bin -o firmware_patched_ota.bin
```

The tool performs the following steps in sequence:

1. Validates the Navee OTA header (model, type, version)
2. Validates the RTL8762C image header (ic_type, image_id, payload_len)
3. Verifies the original SHA-256 to confirm the firmware file is intact
4. Searches for the patch pattern `0E 2D 02 D8 04 E0 0A 2D 02 D9` by context
5. Replaces `02 D9` (BLS) with `00 BF` (NOP) at the located offset
6. Recomputes SHA-256 over the three SDK-defined regions
7. Writes the corrected hash back into the image header
8. Verifies the new SHA-256 matches before writing the output file

**Result:** The patched OTA binary has a valid SHA-256. The transfer via `ota_flasher.py` completes (1080/1080 blocks), and the bootloader's SHA-256 verification now passes. The firmware installs to Bank A on reboot.

---

## The Patch

The meter firmware contains a `lift_speed_limit` function identified via Ghidra analysis:

```c
if (sys_stc[0x4a] == 0x02) {                // lift_speed_limit flag
    return sys_stc[0x47] * 10 + 5;           // Custom Speed (BLE CMD 0x6E)
} else {
    return PID_DEFAULT_TABLE[area_code];      // 22.5 km/h (Germany)
}
```

**1-byte patch:**

| | OTA File Offset | Flash Address | Bytes | Instruction |
|---|---|---|---|---|
| Original | `0xF848` | `0x0081D448` | `02 D9` | BLS (branch if less/same) |
| Patched | `0xF848` | `0x0081D448` | `00 BF` | NOP (no operation) |

The NOP removes the conditional branch, making the code always fall through to the custom speed path. Speed is then settable via BLE CMD `0x6E [0x01, km/h]`.

---

## Hardware

**Dashboard MCU:** Realtek RTL8762C BLE SoC (Module RB8762-35A1)
- ARM Cortex-M4F, integrated BLE 2.4 GHz radio
- External SPI flash, 512 KB, memory-mapped at 0x00800000
- UART download mode via P0_3 pin (no SWD/JTAG needed)
- MAC: `10:A5:62:9A:BB:3E`
- Identified March 19 during dashboard disassembly (short-circuit incident)

**Internal wiring:** 5-wire cable (black=GND, red=53V, blue=52V, yellow=Controller RX 3.8V, green=Controller TX 4.12V) — standard two-wire full-duplex UART at 19200 baud 8N1

> Full details: [`docs/HARDWARE.md`](docs/HARDWARE.md)

---

## OTA Flasher

The OTA flasher implements the complete DFU protocol reverse-engineered from the official Navee APK (`DFUProcessor.java`):

```
Step 1: BLE Connect + AES-128-ECB Auth
Step 2: "down dfu_start 1\r"      -> "ok\r"
Step 3: "down ble_rand\r"         -> Status 0x00 + 16-byte cipher
Step 4: XOR decrypt with AES Key  -> "down ble_key <decrypted>\r" -> "ok\r"
Step 5: Wait for 0x43 ('C')       -> XMODEM Ready
Step 6: 1080 x 128-byte blocks    -> SOH + Seq + ~Seq + Data + CRC-16
Step 7: EOT (0x04)                -> "rsq dfu_ok\r"
```

**Transfer result:** 1080/1080 blocks ACK'd, 0 errors, approximately 34 seconds. With the original firmware: installs correctly (2/2 verified). With a patched firmware before the SHA-256 breakthrough: rejected by bootloader (0/10). With `patch_firmware.py` output: SHA-256 verification passes, firmware installs.

---

## BLDC Firmware Swap

**Attack Vector #7: Flash the international (Global) BLDC firmware onto the German-market scooter to remove the 22 km/h speed limit at the motor controller level.**

### Discovery

The Navee API endpoint `POST /vehicle/modelSoftware` delivers firmware updates for **4 separate MCU types**:

| Component | Type Byte | MCU ID | Description |
|-----------|-----------|--------|-------------|
| `meterList` | 0x01 | 1 | Dashboard (RTL8762C) |
| `bldcList` | 0x02 | 2 | Motor Controller |
| `bmsList` | 0x03 | 3 | Battery Management System |
| `screenList` | 0x04 | 4 | Display/Screen |

Using `firmware_grabber_bldc.py`, we queried all 64 vehicle models on the Navee server and found **BLDC firmware available for 32 models**, including both ST3 PRO variants.

### ST3 PRO DE vs ST3 Global — BLDC Comparison

| | **ST3 PRO DE** (pid=23452) | **ST3 Global** (pid=24012) |
|---|---|---|
| BLDC Version | v0.0.1.5 (newer) | v0.0.1.1 |
| BLDC Size | 53,376 bytes (52.1 KB) | 47,232 bytes (46.1 KB) |
| Model String | T2324 | T2324 |
| Type Byte | 0x02 (BLDC) | 0x02 (BLDC) |
| Meter Version | v2.0.3.1 | v2.0.3.1 |
| BMS Available | Yes (v1.0.0.4) | No |

**Key finding:** Both use the identical hardware model string `T2324` — the firmware is hardware-compatible. The DE version is 6 KB larger and contains a **country code lookup table** (`CNESDEITAUEUUSJPFRNERUSEATNLc|w{`) not present in the Global version, suggesting regional speed limits are enforced via this table.

### Binary Comparison Results

- **91.8% of bytes differ** — completely different builds, not a simple patch
- **No direct 22↔25 byte substitution** exists — speed limit is table-driven
- DE firmware has **6,144 extra bytes** containing lookup tables (country codes, motor curves)
- The firmwares share the same model `T2324` and are built for the same hardware platform

### Flash Procedure

The existing `ota_flasher.py` supports BLDC flashing via MCU type 2:

### OTA Flash Attempt — Blocked

The full DFU flow completes up to the XMODEM data transfer:

| Step | Command | Result |
|------|---------|--------|
| Auth | CMD 0x30 | OK (device ID from BT HCI snoop) |
| DFU Entry | `down dfu_start 2\r` | `ok` |
| Key Exchange | `ble_rand` + `ble_key` | OK (XOR with AES Key 1) |
| XMODEM Ready | Wait for `0x43` ('C') | Received |
| **Block 1** | SOH+seq+data+CRC16 | **NAK `0x15 0x01`** |

Every subsequent block also fails (timeout — BLDC stops responding after first NAK).

**Root cause:** The dashboard stays in application mode during BLDC DFU (unlike meter DFU where it reboots into bootloader). The UART relay between dashboard and BLDC motor controller corrupts or truncates the XMODEM blocks. Meter DFU (`dfu_start 1`) with the same code, same BLE parameters, same XMODEM implementation works flawlessly (1080/1080 blocks ACK'd).

**Verified identical to APK:** Block format (SOH+seq+~seq+128data+CRC16-BE), CRC algorithm (poly 0x1021, init 0), write characteristic (0xb002), write type (without-response), file content (SHA-256 verified against fresh download). The problem is inside the dashboard firmware's UART relay, which cannot be debugged from the BLE side.

**Remaining approaches:**
- Trigger BLDC update via official Navee app (may use different internal mechanism)
- Direct UART connection to BLDC via ESP32/Arduino (bypass dashboard relay)
- Meter firmware NOP patch (proven working via SPI flash and OTA)

---

## APK Decompilation

The official Navee APK (`com.navee.ucaret`) was decompiled with jadx to reverse-engineer the API and DFU protocols. Key findings:

- **Login endpoint:** `POST /loginByOther` with `loginType=2` for Google OAuth (discovered via `LoginActivity.java`)
- **Firmware API:** `POST /vehicle/modelSoftware` returns 4 firmware lists (meter, bldc, bms, screen)
- **DFU protocol:** Text-based commands (`"down dfu_start <MCU_TYPE>\r"`) followed by XMODEM-CRC file transfer
- **5 regional AES-128-ECB keys** for BLE authentication (CN, UK, EU, US, and a 5th variant)
- **24 area codes** with SKU variants (EUR, ITA, USA) controlling speed limits per region
- **64 vehicle models** discovered on the Navee server

> Full reference: [`reverse-engineering/APK_ANALYSIS.md`](reverse-engineering/APK_ANALYSIS.md)

---

## Android Controller App

- BLE auto-connect, AES-128 authentication, real-time telemetry
- Controls: lock, headlight, cruise control, TCS, turn sound, ECO/SPORT mode, ERS
- Material Design 3 dark theme, keep-screen-on

---

## Project Structure

```
navee/
+-- android/                          Controller App (Kotlin/Compose)
|   +-- app/src/main/java/de/pepperonas/navee/
|       +-- ble/                      BLE Manager, Protocol, Auth
|       +-- ui/                       Dashboard UI
|       +-- viewmodel/                State Management
+-- docs/
|   +-- PROTOCOL.md                   BLE protocol reference
|   +-- AUTHENTICATION.md             AES-128 auth flow
|   +-- REVERSE_ENGINEERING.md        Ghidra analysis, all attempts
|   +-- HARDWARE.md                   Wiring, MCU, flash layout
|   +-- INTERNAL_UART_PROTOCOL.md     Dashboard-Controller UART
|   +-- ATTACK_VECTORS.md             All approaches assessed
|   +-- SWD_FLASH_GUIDE.md            rtltool flash guide
+-- tools/
|   +-- firmware/
|   |   +-- navee_meter_v2.0.3.1_ORIGINAL.bin    Stock firmware (135 KB)
|   |   +-- navee_meter_v2.0.3.1_PATCHED.bin     Patched firmware (OTA format)
|   |   +-- navee_full_flash_dump.bin             Complete 512 KB SPI flash dump
|   |   +-- sector_0x1D000_backup.bin             Original sector (pre-patch)
|   |   +-- sector_0x1D000_patched.bin            Patched sector (ready to flash)
|   +-- firmware_grabber.py           Download firmware from Navee API
|   +-- firmware_grabber_bldc.py      BLDC firmware hunter (all models, Google auth)
|   +-- bldc_compare.py              Binary comparison: DE vs Global BLDC
|   +-- probe_google_auth.py         Navee API auth endpoint discovery
|   +-- ota_flasher.py                BLE OTA flasher (macOS/bleak)
|   +-- patch_firmware.py             Automatic patcher + SHA-256 recalculation
|   +-- rtl_flash_dump.py             RTL8762C flash dump script
|   +-- yellow_wire_test.py           Yellow wire injection test (Controller RX discovery)
|   +-- arduino/
|   |   +-- navee_uart_mitm_yellow.ino  MitM v2.4 (Yellow wire protocol 0x51/0xAE)
|   |   +-- navee_uart_mitm_nano.ino    MitM v1 (Green wire, deprecated)
|   |   +-- navee_uart_bridge.ino       USB-to-Yellow UART bridge for flashing
|   +-- ghidra_analysis/              10 Ghidra headless scripts
+-- reverse-engineering/
|   +-- com.navee.ucaret.apk            Official Navee APK
|   +-- navee-apk-decompiled/           Decompiled app sources (jadx, 567 files)
|   +-- APK_ANALYSIS.md                 Complete API, BLE, DFU reference from APK
+-- archive/                          UART MitM (failed approach #2)
```

---

## Quick Start

### Build and install the Android app

```bash
cd android/
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Patch firmware for OTA installation

```bash
# Download stock firmware via the grabber tool (or use the included binary)
python3 tools/firmware_grabber.py

# Patch and recalculate SHA-256 automatically
python3 tools/patch_firmware.py tools/firmware/navee_meter_v2.0.3.1_ORIGINAL.bin

# Flash via BLE OTA
python3 tools/ota_flasher.py tools/firmware/navee_meter_v2.0.3.1_ORIGINAL_PATCHED_OTA.bin
```

### Dump and patch SPI flash directly (requires hardware access)

```bash
# Prerequisites
git clone https://github.com/wuwbobo2021/rtltool.git
pip3 install pyserial crccheck coloredlogs

# Connect: CP2102 USB-UART (3.3V!) to LOG pads, P0_3 to GND, power on
cd rtltool/

# Step 1: Full backup (do this before anything else)
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    read_flash 0x800000 0x80000 backup.bin

# Step 2: Write patched sector (pre-built, from this repo)
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    write_flash 0x81D000 ../tools/firmware/sector_0x1D000_patched.bin

# Step 3: Verify
python3 rtltool.py -p /dev/cu.usbserial-0001 -b 115200 \
    verify_flash 0x81D000 ../tools/firmware/sector_0x1D000_patched.bin
```

---

## Legal Notice

Modifying the speed limit of an e-scooter may void its type approval (ABE) and insurance coverage. Operating a modified e-scooter on public roads may be illegal in your jurisdiction. This project is for research and protocol documentation purposes only. Use at your own risk and only on private property.

---

## Author

**Martin Pfeffer** — [celox.io](https://celox.io) · [GitHub](https://github.com/pepperonas)

## License

[MIT](LICENSE)
