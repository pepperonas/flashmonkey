# Navee ST3 Pro — Scooter Toolkit

<p align="center">
  <img src="docs/banner.png" alt="Navee ST3 Pro Scooter Toolkit" width="100%">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-brightgreen.svg)](android/)
[![Language](https://img.shields.io/badge/Language-Kotlin-purple.svg)](https://kotlinlang.org/)
[![Arduino](https://img.shields.io/badge/Arduino-Nano-00979D.svg)](reverse-engineering/navee_uart_mitm_nano/)
[![Min SDK](https://img.shields.io/badge/Min%20SDK-26-blue.svg)]()
[![Target SDK](https://img.shields.io/badge/Target%20SDK-35-blue.svg)]()
[![Compose](https://img.shields.io/badge/Jetpack-Compose-4285F4.svg)]()
[![Material3](https://img.shields.io/badge/Material-Design%203-757575.svg)]()
[![BLE Protocol](https://img.shields.io/badge/BLE-Custom%20Protocol-informational.svg)](docs/PROTOCOL.md)
[![UART Protocol](https://img.shields.io/badge/UART-19200%20Baud-orange.svg)](docs/INTERNAL_UART_PROTOCOL.md)
[![Speed Unlock](https://img.shields.io/badge/Speed%20Unlock-Failed%20Attempt-red.svg)](docs/UART_MITM_GUIDE.md)
[![Auth](https://img.shields.io/badge/Auth-AES--128--ECB-9C27B0.svg)](docs/AUTHENTICATION.md)
[![Reverse Engineering](https://img.shields.io/badge/RE-APK%20%2B%20Hardware-FFA726.svg)](docs/REVERSE_ENGINEERING.md)
[![Status](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)]()
[![Version](https://img.shields.io/badge/Version-1.0.0-blue.svg)]()
[![Made with](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red.svg)]()
[![Germany](https://img.shields.io/badge/Region-DE-000000.svg)]()

---

Custom Android App, Reverse Engineering & Protokoll-Dokumentation für den **Navee ST3 Pro** E-Scooter.

Dieses Projekt dokumentiert das proprietäre BLE- und UART-Protokoll des Navee ST3 Pro und stellt eine eigene Android-App bereit, die den Scooter unabhängig von der offiziellen Navee-App steuert. Zusätzlich wurde das interne UART-Protokoll zwischen Dashboard und Controller reverse-engineered — Grundlage für ESP32-basiertes Hardware-Tuning.

---

## Features

### Android App

- **BLE-Verbindung** — Automatisches Scannen und Verbinden mit dem Scooter
- **Authentifizierung** — AES-128-ECB basierte Auth (5 Keys, kompatibel mit offiziellem Protokoll)
- **BLE-Verbindung** — Auto-Connect per gespeicherter MAC, Fallback auf BLE-Scan
- **Authentifizierung** — AES-128-ECB Auth mit Device-ID aus BT-Capture
- **Echtzeit-Telemetrie** — Geschwindigkeit, Akku, Restreichweite, Spannung
- **Steuerung** — Sperre, Licht (Auto-Sensor), Tempomat, TCS, Blinker-Ton
- **Fahrmodus** — ECO / SPORT umschaltbar
- **ERS (Rekuperation)** — Niedrig (30) / Mittel (60) / Hoch (90)
- **Info-Sheet** — Funktionsübersicht aller Steuerungselemente
- **Material Design 3** — Dark Theme mit Jetpack Compose

### Hardware Reverse Engineering

- **UART-Protokoll** zwischen Dashboard und Controller entschlüsselt (19200 Baud, 8N1)
- **Drei Frame-Typen** identifiziert (Dashboard-Status, Telemetrie, Controller-Telemetrie)  
- **Speed-Limits** in Frame A lokalisiert — aber Controller ignoriert diese Werte
- **Arduino MitM** implementiert und getestet — **erfolglos** (Limits firmware-seitig hardcoded)

---

## Projektstruktur

```
navee/
├── README.md                  ← Du bist hier
├── LICENSE                    ← MIT Lizenz
├── .gitignore
├── android/                   ← Android App (Kotlin, Jetpack Compose)
│   ├── app/
│   ├── build.gradle.kts
│   ├── gradle/
│   ├── gradle.properties
│   ├── gradlew
│   └── settings.gradle.kts
├── docs/                      ← Protokoll-Dokumentation
│   ├── PROTOCOL.md            ← BLE-Protokoll Referenz
│   ├── INTERNAL_UART_PROTOCOL.md ← Internes UART-Protokoll (Dashboard ↔ Controller)
│   ├── AUTHENTICATION.md      ← Authentifizierungsablauf
│   └── REVERSE_ENGINEERING.md ← Reverse-Engineering Ergebnisse
├── reverse-engineering/       ← Tools und Skripte zur Analyse
│   └── README.md
└── tools/                     ← Firmware-Grabber und Analyse-Scripts
    └── README.md
```

---

## Schnellstart

### Voraussetzungen

- Android Studio Hedgehog oder neuer
- Android SDK 26+ (Android 8.0)
- Ein Navee ST3 Pro E-Scooter in BLE-Reichweite

### Bauen & Installieren

```bash
cd android/
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

Alternativ: Projekt in Android Studio öffnen (`android/` Verzeichnis) und über Run starten.

### Berechtigungen

Die App benötigt folgende Berechtigungen:
- `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT` — BLE-Kommunikation
- `ACCESS_FINE_LOCATION` — Erforderlich für BLE-Scanning auf Android 12+

---

## Protokoll-Übersicht

Der Navee ST3 Pro kommuniziert über **Bluetooth Low Energy (BLE)** mit einem proprietären Binärprotokoll:

| Element | Wert |
|---------|------|
| Service UUID | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Write Characteristic | `0000b002-0000-1000-8000-00805f9b34fb` |
| Notify Characteristic | `0000b003-0000-1000-8000-00805f9b34fb` |
| Frame-Header | `55 AA` |
| Frame-Footer | `FE FD` |

Jeder Frame hat folgendes Format:
```
[55 AA] [Flag] [CMD] [LEN] [DATA...] [Checksum] [FE FD]
```

Die vollständige Protokoll-Dokumentation befindet sich in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

---

## Rechtlicher Hinweis

> **Geschwindigkeitsbegrenzungen:** Der Navee ST3 Pro unterliegt in Deutschland einer firmware-seitigen Geschwindigkeitsbegrenzung von **22 km/h**. Diese Begrenzung ist im Controller-Firmware-Code fest verankert (PID-abhängig) und kann **nicht** per BLE- oder UART-Manipulation umgangen werden. Tests mit UART-MitM zeigten, dass der Controller Dashboard-Speed-Limits komplett ignoriert.

> Dieses Projekt dient ausschließlich der Forschung, Protokoll-Dokumentation und dem Zugang zu Funktionen, die die offizielle App ebenfalls bietet — unabhängig von den Navee-Servern.

---

## Autor

**Martin Pfeffer** — [GitHub](https://github.com/pepperonas)

---

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
