[English](ATTACK_VECTORS.md) | [Deutsch](ATTACK_VECTORS_DE.md)

# Attack Vectors — Navee ST3 Pro Speed Limit

Honest assessment of all attempted approaches to modify the 22 km/h speed limit (PID 23452, German market).

## Summary Table

| # | Vector | Status | Effort | Risk |
|---|--------|--------|--------|------|
| 1 | BLE CMD 0x6E (Max Speed) | Failed | Low | None |
| 2 | UART MitM (Arduino) | Failed | Medium | Low |
| 3 | Firmware Patch (Ghidra) | Patch Found | High | N/A |
| 4 | OTA Flash (BLE XMODEM) | SHA-256 Cracked | Very High | Low |
| 5 | SPI Flash Direct (rtltool) | Verified | Medium | Medium |
| 6 | Controller Swap (AliExpress) | Proven | Low | Low |
| 7 | Speed Limiter Wire | N/A (new revision) | Low | Low |
| 8 | OTA with SHA-256 Fix | Ready (untested) | Medium | Low |

## Detailed Analysis

### 1. BLE Command 0x6E — Max Speed Setting
**Status: Failed**

The official Navee app sends CMD 0x6E with payload [0x01, speed_kmh] to set the maximum speed. The scooter ACKs the command but completely ignores it. The `lift_speed_limit` flag in the firmware (at sys_stc[0x4A]) must be set to 0x02 for CMD 0x6E to take effect. Without the firmware patch, this flag is never set for PID 23452.

**Why it fails:** The speed limit function (FUN_0800ad02) checks the area code (derived from PID). For Germany (area code 3), it returns 22.5 km/h regardless of the CMD 0x6E value. Only when `lift_speed_limit == 0x02` does it use the custom speed from sys_stc[0x47].

### 2. UART MitM — Arduino Interceptor
**Status: Failed**

An Arduino UNO was placed as man-in-the-middle on the green UART wire between dashboard and motor controller. The Arduino parsed Frame A (dashboard status, 15 bytes) and modified bytes 6-7 (speed values) from 0x17/0x15 to 0x1E/0x1E (30 km/h), recalculating the checksum.

Over 1168 frames were successfully modified with correct checksums. The motor controller received and processed these frames. **But the scooter still rode at exactly 22 km/h.**

**Why it fails:** The speed bytes in Frame A (bytes 6-7) are NOT speed limits — they are telemetry/display values that the dashboard sends to the controller. The actual speed limit is computed inside the dashboard firmware and enforced through a different mechanism (likely the motor PWM/current limit parameters, not these specific bytes).

**Key insight:** The controller does NOT accept externally manipulated frames for speed limit changes. The speed limit must come from the dashboard firmware itself, sent as an authentic calculation result.

### 3. Firmware Patch — Ghidra Analysis
**Status: Patch Identified (not yet installed)**

Using Ghidra headless analysis on the downloaded meter firmware (v2.0.3.1, 138240 bytes), the speed limit function was identified:

```
FUN_0800ad02 (File offset: 0xAD02):
  if (sys_stc[0x4A] == 0x02) {        // lift_speed_limit flag
      return sys_stc[0x47] * 10 + 5;  // Custom speed from BLE CMD 0x6E
  } else {
      return PID_DEFAULT_TABLE[area_code];  // 22.5 km/h for Germany
  }
```

**The Patch (1 byte):**
- File Offset 0xF848: `02 D9` (BLS — branch if less/same) → `00 BF` (NOP)
- This removes the conditional branch, making the code always fall through to the custom speed path
- After patching, CMD 0x6E can set any speed value

### 4. OTA Flash — BLE XMODEM Transfer
**Status: SHA-256 Checksum Cracked (2026-03-20)**

The OTA flasher was fully developed and verified:
- Complete DFU protocol: `dfu_start` → `ble_rand` → `ble_key` → XMODEM → EOT
- APK-exact state machine (asyncio.Event, ACK block validation)
- 1080/1080 blocks transferred successfully (135 KB, 34-68 seconds)
- Original firmware: `rsq dfu_ok` received, firmware installed (2/2 attempts)
- **ANY modified firmware: rejected (0/10 attempts)** — prior to SHA-256 fix

Even changing a single byte in the 0xFF padding area caused rejection. The bootloader uses SHA-256 for integrity checking.

**SHA-256 cracked on 2026-03-20.** The algorithm and its exact placement in the firmware image were found by reviewing the Realtek Bee2 SDK source (`silent_dfu_flash.c`). A patched OTA firmware binary with a correctly recalculated SHA-256 has been produced: `navee_meter_v2.0.3.1_PATCHED_OTA.bin`. OTA patching is now theoretically possible but has not yet been tested on a working dashboard — the test board was damaged by a short circuit before end-to-end OTA testing could be completed.

**Checksums tested before solution (all failed to match):**
CRC-16/XMODEM, CRC-16/CCITT, CRC-16/ARC, CRC-16/MODBUS, CRC-32 (standard), CRC-32 (STM32), XOR-32 (word), XOR-8 (byte), SUM-8, SUM-16, SUM-32, Fletcher-16, Fletcher-32, Adler-32, MD5, SHA-1, SHA-256, HMAC-MD5 (with all 5 AES keys), Brute-force CRC-32 at every 4-byte position, Brute-force CRC-16 at every 2-byte position.

### 5. SPI Flash Direct — rtltool via UART
**Status: Verified**

The dashboard MCU is a Realtek RTL8762C which can be programmed via UART when pin P0_3 is held LOW during boot. Using [rtltool](https://github.com/wuwbobo2021/rtltool), the entire SPI flash can be read and written, bypassing the OTA bootloader's integrity check.

**Verified results:**
- Full 512 KB flash dump completed successfully via rtltool
- Patch byte written to flash address `0x0081D448` (the `02 D9` → `00 BF` substitution)
- Patch verified by re-reading the flash sector after write

**Procedure used:**
1. Opened dashboard, powered via Arduino 3.3V supply (scooter battery isolated)
2. Connected CP2102 USB-UART adapter (3.3V logic)
3. Bridged P0_3 to GND with a jumper wire, applied power → RTL8762C entered download mode
4. Dumped entire 512 KB flash (backup)
5. Located firmware using `T2202` header; patch target confirmed at `0x0081D448`
6. Wrote patched sector back via rtltool
7. Verified by re-reading the patched address

**Note:** The test board had been damaged by a short circuit prior to this work (scooter was ON during PCB removal). Flash operations succeeded on the damaged board; functional verification of the patched firmware awaits a working replacement dashboard.

### 6. Controller Swap — Global Version
**Status: Proven (by community)**

Replacing the motor controller with a "Global" version (without DE speed limit) removes the 22 km/h restriction. Controllers are available on AliExpress for ~30-50 EUR.

**Pros:** Proven to work, no firmware knowledge needed
**Cons:** Cost, voiding warranty, different controller behavior possible

Source: rollerplausch.com community

### 7. Speed Limiter Wire — Hardware Disconnect
**Status: Not Applicable (new revision)**

Older hardware revisions had a dedicated white wire that, when cut, removed the speed limit. Current revisions (2024+) no longer have this wire. The speed limit is now entirely firmware-enforced.

Source: rollerplausch.com community

### 8. OTA with SHA-256 Fix
**Status: Ready (untested)**

Following the SHA-256 crack documented in Vector 4, a Python script (`patch_firmware.py`) has been written that automates the full patching workflow:

1. Takes any Navee meter firmware binary as input
2. Applies the speed limit patch (`02 D9` → `00 BF` at the correct offset)
3. Recalculates the SHA-256 checksum using the algorithm from the Realtek Bee2 SDK (`silent_dfu_flash.c`)
4. Writes the corrected checksum back into the binary at the expected header location
5. Outputs a ready-to-flash OTA binary

The output file `navee_meter_v2.0.3.1_PATCHED_OTA.bin` is the result of running `patch_firmware.py` against the official v2.0.3.1 firmware. End-to-end OTA testing (transfer → bootloader acceptance → boot) has not yet been performed because the test board was damaged before this step could be reached.

## Recommendations

**For new users:** OTA with SHA-256 fix (Vector 8) is now the recommended approach. It requires no hardware access — only a BLE connection and the `patch_firmware.py` script. The SHA-256 algorithm is solved, and the patched binary is ready. End-to-end OTA testing is the one remaining step before this path is fully confirmed.

**For most users (proven today):** Controller swap (Vector 6) is still the simplest confirmed working solution.

**For reverse engineers:** SPI flash direct programming (Vector 5) is fully verified. The flash was dumped and patched successfully. It requires opening the dashboard and accessing the UART/P0_3 pads, but bypasses the bootloader integrity check entirely. Functional verification on a working board is still needed.

**Not recommended:** Manual OTA checksum hunting without using `patch_firmware.py`. The SHA-256 algorithm is now known — further brute-force attempts are unnecessary.
