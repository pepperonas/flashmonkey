[English](README.md) | [Deutsch](README_DE.md)

# Navee ST3 Pro — Reverse Engineering & Custom Firmware

<p align="center">
  <img src="docs/banner.png" alt="Navee ST3 Pro Scooter Toolkit" width="100%">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-brightgreen.svg)](android/)
[![Kotlin](https://img.shields.io/badge/Kotlin-2.1-purple.svg)](https://kotlinlang.org/)
[![Compose](https://img.shields.io/badge/Jetpack-Compose-4285F4.svg)]()
[![BLE](https://img.shields.io/badge/BLE-Custom%20Protocol-informational.svg)](docs/PROTOCOL.md)
[![MCU](https://img.shields.io/badge/MCU-RTL8762C-FF6F00.svg)](docs/HARDWARE.md)
[![Firmware](https://img.shields.io/badge/Firmware-1--Byte%20Patch-00C853.svg)](docs/REVERSE_ENGINEERING.md#der-patch-1-byte)
[![Flash](https://img.shields.io/badge/SPI%20Flash-Verified-00C853.svg)](#spi-flash-direct-patch)
[![Auth](https://img.shields.io/badge/Auth-AES--128--ECB-9C27B0.svg)](docs/AUTHENTICATION.md)
[![SHA256](https://img.shields.io/badge/SHA--256-Cracked-00C853.svg)](#patch_firmwarepy--automatic-ota-patcher)
[![OTA](https://img.shields.io/badge/OTA%20Patch-Ready-00C853.svg)](#patch_firmwarepy--automatic-ota-patcher)
[![SPI](https://img.shields.io/badge/SPI%20Flash-Verified-00C853.svg)](#spi-flash-direct-patch)
[![RTL](https://img.shields.io/badge/MCU-RTL8762C-FF6F00.svg)](docs/HARDWARE.md)
[![Speed](https://img.shields.io/badge/Speed%20Unlock-Working-00C853.svg)](#the-patch)

---

Reverse engineering, firmware analysis, and Android controller app for the **Navee ST3 Pro** e-scooter (PID 23452, DE market).

This project has fully reverse-engineered the proprietary BLE protocol, developed an independent controller app, analyzed the meter firmware with Ghidra, built a working OTA flasher, dumped the complete SPI flash via UART, **successfully written a 1-byte firmware patch directly to flash** using [rtltool](https://github.com/wuwbobo2021/rtltool), **cracked the RTL8762C SHA-256 checksum algorithm**, and created `patch_firmware.py` — a fully automated tool that patches any firmware version and produces a valid OTA binary.

---

## Attack Vectors

| # | Approach | Result |
|---|----------|--------|
| 1 | BLE CMD `0x6E` (Max Speed) | Failed — ACK'd but ignored by firmware |
| 2 | UART MitM (Arduino) | Failed — Controller ignores manipulated frames |
| 3 | **Firmware Patch (Ghidra)** | **Verified — 1-byte NOP enables custom speed mode** |
| 4 | OTA Flash (BLE XMODEM) | Failed — Transfer OK, bootloader rejected all 10 patched attempts |
| 5 | **SPI Flash Direct (rtltool)** | **Verified — Patch written and confirmed via read-back** |
| 6 | Controller Swap (AliExpress) | Verified by community |

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

**Internal wiring:** 5-wire cable (black=GND, red=53V, blue=52V, yellow=unknown, green=UART 19200 baud)

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
|   +-- ota_flasher.py                BLE OTA flasher (macOS/bleak)
|   +-- patch_firmware.py             Automatic patcher + SHA-256 recalculation
|   +-- rtl_flash_dump.py             RTL8762C flash dump script
|   +-- ghidra_analysis/              10 Ghidra headless scripts
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
