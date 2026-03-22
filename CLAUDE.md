# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Navee ST3 Pro Scooter Toolkit - Custom Android app and reverse-engineered BLE/UART protocol documentation for the Navee ST3 Pro E-Scooter. The project provides an independent control app that doesn't rely on Navee servers, plus documentation of the proprietary protocols.

## Build Commands

### Android App
```bash
cd android/

./gradlew assembleDebug                                    # Debug APK
./gradlew assembleRelease                                  # Release APK (ProGuard enabled)
adb install app/build/outputs/apk/debug/app-debug.apk     # Install on device
./gradlew clean                                            # Clean build
```

### Python Tools (no venv needed)
```bash
python3 tools/firmware_grabber.py      # Download OTA firmware
python3 tools/ota_flasher.py           # Flash firmware via BLE OTA
python3 tools/patch_firmware.py        # Patch firmware binary
python3 tools/test_speed_set.py        # Protocol test: speed setting
```

No automated test suite exists — protocol tests in `tools/test_*.py` are manual BLE integration scripts.

## Architecture

### Data Flow
```
Scooter ←BLE→ NaveeBleManager → ScooterViewModel (StateFlow) → DashboardScreen (Compose)
```

- `NaveeApp` initializes `NaveeAuth` on startup (AES keys from SharedPreferences)
- `MainActivity` requests BLE permissions, creates `ScooterViewModel` via `by viewModels()`
- `NaveeBleManager` handles scanning, GATT connection, notification subscription, and frame reassembly
- `NaveeProtocol` builds/parses binary frames — all parsers account for `data[0]` being a version byte (payload at `data[1]+`)
- `ScooterViewModel` exposes `StateFlow<ScooterState>` and `StateFlow<ScooterTelemetry>` consumed by Compose UI
- Screen stays awake (`FLAG_KEEP_SCREEN_ON`) while the app is visible

### PID-Dependent Behavior
The scooter's Product ID (PID), extracted from BLE scan record bytes 6-8, determines available speed options and firmware-enforced limits. `ScooterViewModel.getMaxSpeedOptionsForPID()` maps known PIDs to their allowed speed lists. Unknown PIDs get a generic fallback.

### Key Protocol Details
- **BLE Service UUID**: `0000d0ff-3c17-d293-8e48-14fe2e4da212`
- **Write Char**: `0000b002-...`, **Notify Char**: `0000b003-...`
- **Frame Format**: `[55 AA] [Flag] [CMD] [LEN] [DATA...] [Checksum] [FE FD]`
- **Authentication**: AES-128-ECB with 5 rotating keys, device ID from BT capture
- **UART** (internal, dashboard↔controller): 19200 baud, 8N1, 3.3V logic

### Protocol Documentation
- `docs/PROTOCOL.md` — BLE command reference (all docs have `_DE.md` German translations)
- `docs/INTERNAL_UART_PROTOCOL.md` — Internal UART between dashboard and motor controller
- `docs/AUTHENTICATION.md` — Auth flow and key rotation
- `docs/REVERSE_ENGINEERING.md` — Hardware teardown findings

### Tools Directory (`tools/`)
- `firmware_grabber.py` / `ota_flasher.py` / `patch_firmware.py` — Firmware download, OTA flash, binary patching
- `ghidra_area_code.py` — Ghidra script for firmware analysis
- `rtl_rom_dump.py` / `rtl_flash_dump.py` — RTL chipset memory dumping
- `test_speed_set.py` / `test_speed_raw.py` / `test_eot.py` — Manual BLE protocol tests
- `tools/arduino/` — Arduino/ESP32 sketches for hardware interfacing

### Critical Implementation Notes
- Response `data[0]` is a version/type byte — actual payload starts at `data[1]`
- Checksum: sum of all bytes from header to data end, modulo 256
- Auth credentials (device ID, post-auth params) must be extracted from a BT capture and entered manually on first run
- **UART danger**: Red/Blue wires on dashboard connector carry **53V/52V battery voltage** — never connect to microcontroller

## Android Requirements
- Min SDK 26, Target SDK 35, Java 17, Kotlin 2.1.0, Compose BOM 2024.12.01
- Release builds use ProGuard minification

## Legal Compliance Note
The Navee ST3 Pro has a firmware-enforced speed limit of 22 km/h (Germany/EU regulation). This limit is PID-dependent and cannot be bypassed via BLE commands. This project focuses on documenting the protocol and providing server-independent access to existing scooter functions.