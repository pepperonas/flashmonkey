# Navee ST3 Pro — Custom Firmware & Controller App

<p align="center">
  <img src="docs/banner.png" alt="Navee ST3 Pro Scooter Toolkit" width="100%">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-brightgreen.svg)](android/)
[![Kotlin](https://img.shields.io/badge/Kotlin-2.1-purple.svg)](https://kotlinlang.org/)
[![Compose](https://img.shields.io/badge/Jetpack-Compose-4285F4.svg)]()
[![BLE](https://img.shields.io/badge/BLE-Custom%20Protocol-informational.svg)](docs/PROTOCOL.md)
[![OTA Flash](https://img.shields.io/badge/OTA-Transfer%20OK-FFA726.svg)](tools/ota_flasher.py)
[![Firmware](https://img.shields.io/badge/Firmware-1--Byte%20Patch-00C853.svg)](docs/REVERSE_ENGINEERING.md#der-patch-1-byte)
[![Ghidra](https://img.shields.io/badge/Ghidra-ARM%20Cortex--M-FFA726.svg)](tools/ghidra_analysis/)
[![Auth](https://img.shields.io/badge/Auth-AES--128--ECB-9C27B0.svg)](docs/AUTHENTICATION.md)
[![Made with](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red.svg)]()

---

Reverse Engineering, Custom Firmware und Android Controller-App für den **Navee ST3 Pro** E-Scooter.

Dieses Projekt hat das proprietäre BLE-Protokoll vollständig reverse-engineered, eine unabhängige Controller-App entwickelt, die Meter-Firmware mit Ghidra analysiert und einen funktionierenden **OTA-Flasher** gebaut. Ergebnis: ein **1-Byte Firmware-Patch** der das `lift_speed_limit`-Flag aktiviert — flashbar über BLE vom MacBook.

---

## Highlights

### OTA-Flash — Transfer verifiziert, Bootloader blockiert Patch
- **1080/1080 Blöcke** erfolgreich übertragen (135 KB, 34-68 Sekunden)
- Vollständiger DFU-Flow: `dfu_start` → XOR Key Exchange → XMODEM Transfer → EOT → `rsq dfu_ok`
- **Original-Firmware wird installiert** (2/2 Versuche erfolgreich)
- **Gepatchte Firmware wird abgelehnt** — Bootloader-Integritätsprüfung (auch 1 Byte im Padding reicht)
- **Nächster Schritt:** SWD/JTAG Direct Flash (umgeht Bootloader)

### 1-Byte Firmware-Patch
- **File Offset `0xF848`**: `02 D9` (bls) → `00 BF` (NOP)
- Aktiviert das eingebaute `lift_speed_limit`-Flag im Dashboard-Controller
- Geschwindigkeit danach frei setzbar via BLE CMD `0x6E [0x01, km/h]`
- **Patch verifiziert**, aber nur per SWD/JTAG installierbar (nicht per OTA)

### Android Controller-App
- BLE Auto-Connect, AES-128 Auth, Echtzeit-Telemetrie
- Steuerung: Sperre, Licht, Tempomat, TCS, Blinker-Ton, ECO/SPORT, ERS
- Material Design 3 Dark Theme, Keep-Screen-On

### Reverse Engineering Chronologie
| # | Ansatz | Ergebnis |
|---|--------|----------|
| 1 | BLE CMD `0x6E` (Max Speed) | ❌ ACK'd aber ignoriert |
| 2 | UART MitM (Arduino Nano) | ❌ Controller ignoriert externe Frame-Manipulation |
| 3 | **Firmware-Patch (Ghidra)** | ✅ **1-Byte NOP aktiviert Custom-Speed-Modus** |
| 4 | OTA-Flash (macOS) | ⚠️ Transfer OK, Bootloader-Checksumme blockiert Patch |
| 5 | **SWD/JTAG Direct Flash** | ⏳ **Nächster Schritt** — umgeht Bootloader |

---

## Projektstruktur

```
navee/
├── android/                     ← Controller-App (Kotlin/Compose)
│   └── app/src/main/java/de/pepperonas/navee/
│       ├── ble/                 ← BLE Manager, Protokoll, Auth
│       ├── ui/                  ← Dashboard UI
│       └── viewmodel/           ← State Management
├── docs/
│   ├── PROTOCOL.md              ← BLE-Protokoll (Commands, Status, Telemetrie, DFU)
│   ├── AUTHENTICATION.md        ← AES-128 Auth-Flow
│   ├── REVERSE_ENGINEERING.md   ← Ghidra-Analyse, Patch-Details, alle 5 Ansätze
│   └── SWD_FLASH_GUIDE.md       ← SWD/JTAG Direct Flash Anleitung
├── tools/
│   ├── firmware/
│   │   ├── navee_meter_v2.0.3.1_ORIGINAL.bin  ← Original-Firmware (135 KB)
│   │   └── navee_meter_v2.0.3.1_PATCHED.bin   ← Gepatchte Firmware (1 Byte Diff)
│   ├── firmware_grabber.py      ← Firmware von Navee-API herunterladen
│   ├── ota_flasher.py           ← BLE OTA Flasher (macOS/bleak) — VERIFIZIERT
│   └── ghidra_analysis/         ← Ghidra Headless Scripts
└── archive/                     ← UART MitM (gescheiterter Ansatz 2)
```

---

## Schnellstart

### App bauen & installieren

```bash
cd android/
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Firmware flashen (macOS)

Voraussetzung: `pip3 install bleak pycryptodome`

```bash
cd tools/

# 1. Scooter-Info lesen (kein Risiko)
python3 ota_flasher.py --read-info

# 2. DFU-Entry testen (kein Flash, sicher)
python3 ota_flasher.py --test-dfu-entry

# 3. Key Exchange testen (findet den richtigen AES-Key)
python3 ota_flasher.py --test-key-exchange

# 4. Original-Firmware flashen (OTA-Prozess verifizieren)
python3 ota_flasher.py firmware/navee_meter_v2.0.3.1_ORIGINAL.bin

# 5. Gepatchte Firmware flashen (Speed-Limit aufheben)
python3 ota_flasher.py firmware/navee_meter_v2.0.3.1_PATCHED.bin

# 6. Rollback jederzeit
python3 ota_flasher.py firmware/navee_meter_v2.0.3.1_ORIGINAL.bin
```

### Firmware von Navee-Server herunterladen

```bash
python3 tools/firmware_grabber.py
```

---

## OTA-Flash Details

Der OTA-Flasher implementiert das vollständige DFU-Protokoll aus der dekompilierten offiziellen Navee-App:

```
Step 1: BLE Connect + Auth (Device-ID)
Step 2: "down dfu_start 3\r"      → "ok\r"
Step 3: "down ble_rand\r"         → Status 0x00 + 16-Byte Cipher
Step 4: XOR decrypt mit AES Key 1 → "down ble_key <decrypted>\r" → "ok\r"
Step 5: Warte auf 0x43 ('C')      → XMODEM Ready
Step 6: 1080 × 128-Byte Blöcke    → SOH + Seq + ~Seq + Data + CRC-16
Step 7: EOT (0x04)                → "rsq dfu_ok\r"
```

**Verifiziertes Ergebnis:** 1080/1080 Blöcke, 0 Fehler, 34.1 Sekunden, 4049 Bytes/s.

---

## Technische Details

### Der Patch im Detail

Die Meter-Firmware enthält eine `lift_speed_limit`-Funktion (FUN_0800ad02):

```c
if (sys_stc[0x4a] == 0x02) {                // lift_speed_limit Flag
    return sys_stc[0x47] * 10 + 5;           // → Custom Speed!
} else {
    return PID_DEFAULT_TABLE[area_code];      // → 22.5 km/h (DE)
}
```

Der Patch (NOP statt bls) sorgt dafür, dass das Flag **immer** auf Custom steht. Danach bestimmt `sys_stc[0x47]` — setzbar via BLE CMD `0x6E` — die Geschwindigkeit.

→ Vollständige Analyse: [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md#ghidra-analyse-ergebnisse-detailliert)

### BLE-Protokoll

| Element | Wert |
|---------|------|
| Service UUID | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Frame-Format | `[55 AA] [Flag] [CMD] [LEN] [DATA] [Checksum] [FE FD]` |
| Auth | AES-128-ECB, 5 Schlüssel, Device-ID aus BT-Capture |
| DFU | Text-Commands + XMODEM, XOR Key Exchange, CRC-16 |

→ Vollständige Referenz: [`docs/PROTOCOL.md`](docs/PROTOCOL.md)

---

## Rechtlicher Hinweis

> Geschwindigkeitsänderungen am E-Scooter können zum Erlöschen der Betriebserlaubnis führen. Dieses Projekt dient der Forschung und Protokoll-Dokumentation. Nutzung auf eigene Verantwortung.

---

## Autor

**Martin Pfeffer** — [celox.io](https://celox.io) · [GitHub](https://github.com/pepperonas)

## Lizenz

[MIT](LICENSE)
