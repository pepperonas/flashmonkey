# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Navee ST3 Pro Scooter Toolkit - Custom Android app and reverse-engineered BLE/UART protocol documentation for the Navee ST3 Pro E-Scooter. The project provides an independent control app that doesn't rely on Navee servers, plus documentation of the proprietary protocols.

## Build Commands

### Android App
```bash
# Build debug APK
cd android/
./gradlew assembleDebug

# Install on connected device
adb install app/build/outputs/apk/debug/app-debug.apk

# Build release APK
./gradlew assembleRelease

# Clean build
./gradlew clean
```

## Architecture

### Android App Structure
- **Kotlin + Jetpack Compose** - Modern Android stack with Material Design 3
- **BLE Communication** - Located in `android/app/src/main/java/de/pepperonas/navee/ble/`
  - `NaveeBleManager.kt`: Handles BLE scanning, connection, and data exchange
  - `NaveeProtocol.kt`: Protocol constants, frame building/parsing, command definitions
  - `NaveeAuth.kt`: AES-128-ECB authentication implementation
- **UI Layer** - `android/app/src/main/java/de/pepperonas/navee/ui/`
  - `DashboardScreen.kt`: Main UI with real-time telemetry display
- **ViewModel** - `ScooterViewModel.kt`: State management and business logic

### Protocol Documentation
- `docs/PROTOCOL.md`: Complete BLE protocol reference (commands, responses, frame format)
- `docs/INTERNAL_UART_PROTOCOL.md`: Internal UART protocol between dashboard and controller
- `docs/AUTHENTICATION.md`: Authentication flow details
- `docs/REVERSE_ENGINEERING.md`: Hardware analysis and findings

### Key Protocol Details
- **BLE Service UUID**: `0000d0ff-3c17-d293-8e48-14fe2e4da212`
- **Frame Format**: `[55 AA] [Flag] [CMD] [LEN] [DATA...] [Checksum] [FE FD]`
- **Authentication**: AES-128-ECB with 5 rotating keys
- **UART**: 19200 baud, 8N1, 3.3V logic level

## Development Notes

### Android Requirements
- Min SDK 26 (Android 8.0)
- Target SDK 35
- Kotlin 2.1.0
- Jetpack Compose BOM 2024.12.01

### BLE Permissions Required
- `BLUETOOTH_SCAN`
- `BLUETOOTH_CONNECT` 
- `ACCESS_FINE_LOCATION` (for BLE scanning on Android 12+)

### Critical Protocol Implementation Details
- Response data contains a leading version/type byte at `data[0]`
- Actual payload starts at `data[1]` - all byte indices in documentation account for this
- Checksum calculation: sum of all bytes from header to data, modulo 256
- Device ID for auth obtained from BT capture (see `NaveeAuth.kt`)

### Hardware Interfacing
- **UART Pinout** (Dashboard connector):
  - Black: GND
  - Yellow/Green: UART signals (3.3V)
  - Red/Blue: **53V/52V battery lines - DO NOT CONNECT to microcontroller**
- ESP32/Arduino implementations planned in `microcontroller/` directory

## Legal Compliance Note
The Navee ST3 Pro has a firmware-enforced speed limit of 22 km/h (Germany/EU regulation). This limit is PID-dependent and cannot be bypassed via BLE commands. This project focuses on documenting the protocol and providing server-independent access to existing scooter functions.