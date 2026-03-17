# Microcontroller — ESP32 / Arduino

Dieses Verzeichnis ist für Microcontroller-Implementierungen vorgesehen, die direkt mit dem Navee ST3 Pro kommunizieren — über BLE und/oder UART.

## Kommunikationswege

### 1. UART (direkt am Dashboard-Stecker)

Am Dashboard-Kabelbaum wurde eine UART-Schnittstelle identifiziert:

| Ader | Farbe | Funktion |
|------|-------|----------|
| Schwarz | GND | Masse |
| Gelb | UART Signal | 3.3V Logik, Idle-High |
| Grün | UART Signal | 3.3V/5V Logik, Idle-High |

**Vorteil:** Keine BLE-Authentifizierung nötig, direkter Hardware-Zugriff.
**Achtung:** Rot (53V) und Blau (52V) sind Akku-Leitungen — **niemals** an Mikrocontroller anschließen!

Details: [`../docs/REVERSE_ENGINEERING.md`](../docs/REVERSE_ENGINEERING.md#hardware-reverse-engineering--uart-schnittstelle)

### 2. BLE (kabellos)

Protokoll mit AES-Auth, identisch zur Android-App.
Details: [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md)

## Geplante Projekte

- **ESP32 UART-Bridge** — UART am Dashboard abhören und Kommandos senden, ohne BLE-Auth
- **ESP32 BLE Controller** — Standalone-Controller zur kabellosen Steuerung
- **ESP32 Telemetrie-Logger** — Echtzeit-Logging auf SD-Karte oder Display
- **Arduino Dashboard** — OLED/TFT-Display mit Scooter-Telemetrie

## Benötigte Hardware

- ESP32 DevKit oder Arduino mit BLE
- USB-UART-Adapter (3.3V, z.B. CP2102, FT232RL, CH340)
- Logic Level Shifter (falls 5V ↔ 3.3V nötig)
- Dupont-Kabel / Breadboard
