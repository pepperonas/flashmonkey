# Navee ST3 Pro — Scooter Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-brightgreen.svg)](android/)
[![Language](https://img.shields.io/badge/Language-Kotlin-purple.svg)](https://kotlinlang.org/)
[![Min SDK](https://img.shields.io/badge/Min%20SDK-26-blue.svg)]()
[![BLE Protocol](https://img.shields.io/badge/BLE-Custom%20Protocol-informational.svg)](docs/PROTOCOL.md)
[![Status](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)]()
[![Made with](https://img.shields.io/badge/Made%20with-%E2%9D%A4-red.svg)]()

---

Custom Android App, Reverse Engineering & Protokoll-Dokumentation für den **Navee ST3 Pro** E-Scooter.

Dieses Projekt dokumentiert das proprietäre BLE-Protokoll des Navee ST3 Pro und stellt eine eigene Android-App bereit, die den Scooter unabhängig von der offiziellen Navee-App steuert.

---

## Features

### Android App

- **BLE-Verbindung** — Automatisches Scannen und Verbinden mit dem Scooter
- **Authentifizierung** — AES-128-ECB basierte Auth (5 Keys, kompatibel mit offiziellem Protokoll)
- **Echtzeit-Telemetrie** — Geschwindigkeit, Akku, Temperatur, Gesamtstrecke
- **Fahrzeugeinstellungen** — Licht, Tempomat, ERS/Rekuperation, Geschwindigkeitsmodus
- **Speed Mode** — Umschalten zwischen ECO (3) und SPORT (5)
- **Scheinwerfer & Rücklicht** — Einzeln schaltbar
- **Custom Speed Limit** — Benutzerdefinierte Geschwindigkeitsbegrenzung (km/h)
- **Startup Speed** — Anfahrgeschwindigkeit konfigurierbar (0-5, entspricht 0.0-3.0 m/s)
- **Batterie-Status** — Detaillierte Akku-Informationen (37 Bytes)
- **Firmware-Info** — Firmware-Version und Seriennummern auslesen
- **Material Design 3** — Moderne UI mit Jetpack Compose

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
│   ├── AUTHENTICATION.md      ← Authentifizierungsablauf
│   └── REVERSE_ENGINEERING.md ← Reverse-Engineering Ergebnisse
├── reverse-engineering/       ← Tools und Skripte zur Analyse
│   └── README.md
└── microcontroller/           ← ESP32/Arduino Implementierungen (geplant)
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

> **Geschwindigkeitsbegrenzungen:** Der Navee ST3 Pro unterliegt in Deutschland einer firmware-seitigen Geschwindigkeitsbegrenzung von **22 km/h**. Diese Begrenzung ist im Firmware-Code fest verankert (PID-abhängig) und kann nicht per BLE-Kommando umgangen werden. Die Nutzung von E-Scootern im öffentlichen Straßenverkehr unterliegt der eKFV (Elektrokleinstfahrzeuge-Verordnung). Die Manipulation der Höchstgeschwindigkeit ist **nicht** Ziel dieses Projekts.

> Dieses Projekt dient ausschließlich der Forschung, Dokumentation und dem Zugang zu Funktionen, die die offizielle App ebenfalls bietet — unabhängig von den Navee-Servern.

---

## Autor

**Martin Pfeffer** — [celox.io](https://celox.io) | [GitHub](https://github.com/pepperonas)

---

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
