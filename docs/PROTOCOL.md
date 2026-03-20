[English](PROTOCOL.md) | [Deutsch](PROTOCOL_DE.md)

# BLE-Protokoll Dokumentation — Navee ST3 Pro

Vollständige Referenz des proprietären BLE-Kommunikationsprotokolls des Navee ST3 Pro E-Scooters. Basierend auf APK-Dekompilierung (jadx), BT-HCI-Captures und Live-Tests.

---

## Inhaltsverzeichnis

- [BLE UUIDs](#ble-uuids)
- [Frame-Format](#frame-format)
- [Kommando-Übersicht](#kommando-uebersicht)
- [Status-Response (0x70)](#status-response-0x70)
- [Telemetrie](#telemetrie)
- [PID (Product ID)](#pid-product-id)
- [Max-Speed Optionen nach PID](#max-speed-optionen-nach-pid)
- [DFU-Protokoll (Firmware-Update)](#dfu-protokoll-firmware-update-über-ble)

---

## BLE UUIDs

| Typ | UUID |
|-----|------|
| **Service** | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| **Write Characteristic** | `0000b002-0000-1000-8000-00805f9b34fb` |
| **Notify Characteristic** | `0000b003-0000-1000-8000-00805f9b34fb` |

Der Scooter advertised den Service-UUID nicht immer im Scan-Record. Verbindung am besten per gespeicherter MAC-Adresse (Direct Connect).

---

## Frame-Format

```
┌────────┬──────┬─────┬─────┬──────────┬──────────┬────────┐
│ Header │ Flag │ CMD │ LEN │ DATA     │ Checksum │ Footer │
│ 55 AA  │ 1B   │ 1B  │ 1B  │ LEN Byte │ 1B       │ FE FD  │
└────────┴──────┴─────┴─────┴──────────┴──────────┴────────┘
```

| Feld | Länge | Beschreibung |
|------|--------|--------------|
| **Header** | 2 Bytes | Immer `0x55 0xAA` |
| **Flag** | 1 Byte | `0x00` = unverschlüsselt |
| **CMD** | 1 Byte | Kommando-Byte |
| **LEN** | 1 Byte | Länge des DATA-Feldes |
| **DATA** | 0-n Bytes | Nutzlast |
| **Checksum** | 1 Byte | Summe aller Bytes (Header bis DATA) mod 256 |
| **Footer** | 2 Bytes | Immer `0xFE 0xFD` |

**Wichtig:** Die Response-Daten enthalten ein führendes Version/Type-Byte (`data[0]`). Die eigentlichen Nutzdaten beginnen bei `data[1]`. Alle Byte-Indizes in diesem Dokument beziehen sich auf das rohe Data-Array inkl. dieses führenden Bytes.

---

## Kommando-Übersicht

### Schreib-Kommandos (Einzelbyte)

Alle verifiziert gegen die offizielle Navee APK (DeviceAfterFragment.java, DeviceMoreActionActivity.java).

| CMD | Hex | Name | DATA | Status-Byte | Verifiziert |
|-----|-----|------|------|-------------|-------------|
| 80 | `0x50` | Unbind Vehicle | — | — | APK |
| 81 | `0x51` | Lock | `0x00`/`0x01` | data[3] | BT-Capture + Live |
| 82 | `0x52` | Cruise Control | `0x00`/`0x01` | data[4] | Live |
| 83 | `0x53` | ERS (Rekuperation) | `0x1E`=30, `0x3C`=60, `0x5A`=90 | data[6] | Live + Original-App |
| 84 | `0x54` | Taillight (Rücklicht) | `0x00`/`0x01` | data[5] | APK |
| 85 | `0x55` | Mileage Unit | `0x00`=MPH, `0x01`=KM | data[8] | APK |
| 87 | `0x57` | Auto-Headlight (Lichtsensor) | `0x00`/`0x01` | data[9] | BT-Capture + Live (siehe [Licht-Verhalten](#licht-verhalten)) |
| 88 | `0x58` | Speed Mode | `0x03`=ECO, `0x05`=SPORT | data[2] | Live + Original-App |
| 89 | `0x59` | Reset Vehicle | — | — | APK |
| 90 | `0x5A` | Tire Maintenance | `0x01` | — | APK |
| 94 | `0x5E` | Ambient Light | `0x00`/`0x01` (4 Bytes: on,E,D,S) | data[11] | APK |
| 95 | `0x5F` | TCS (Traktionskontrolle) | `0x00`/`0x01` | data[12] | Live + Original-App |
| 96 | `0x60` | Turn Sound (Blinker-Ton) | `0x00`/`0x01` | data[13] | Live |
| 97 | `0x61` | Proximity Key | `0x00`/`0x01` | data[14] | APK |
| 106 | `0x6A` | Startup Speed | `0x00`-`0x05` (0.0-3.0 m/s) | data[20] | APK |
| 107 | `0x6B` | Custom Speed Limit | Bit7=aktiv, Bits0-6=km/h | data[21] | APK |

### Schreib-Kommandos (Mehrbyte)

| CMD | Hex | Name | DATA | Beschreibung |
|-----|-----|------|------|--------------|
| 99 | `0x63` | Set Digit Password | 6 Bytes | 6-stelliges Zahlenpasswort |
| 103 | `0x67` | Light Control | variabel | Erweiterte Lichtsteuerung |
| 109 | `0x6D` | Generic Light | `[typ, state]` | typ: 1=Ambient, 2=Logo, 3=DayRun |
| 110 | `0x6E` | Max Speed | `[0x01, km/h]` | ACK'd, aber Read-Only auf DE-FW |
| 111 | `0x6F` | Set Params | variabel | Post-Auth Parameter |

### Lese-/Status-Kommandos

| CMD | Hex | Name | Response |
|-----|-----|------|----------|
| 112 | `0x70` | Vehicle Settings | 37 Bytes (siehe unten) |
| 113 | `0x71` | Driving/Trip Data | variabel |
| 114 | `0x72` | Battery Status | 37 Bytes |
| 115 | `0x73` | Firmware Version | String |
| 116 | `0x74` | Serial Number | String |
| 117 | `0x75` | Battery SN | String |
| 118 | `0x76` | Drive History | variabel |
| 121 | `0x79` | Battery Extra Info | variabel |

### Authentifizierung

| CMD | Hex | Name | Beschreibung |
|-----|-----|------|--------------|
| 48 | `0x30` | Auth Request | `[keyIndex, 0x00, 6-Byte deviceId, 0x00]` |
| 49 | `0x31` | Auth Key | Challenge-Response (nicht benötigt bei PID 23452) |

### Telemetrie (unaufgefordert)

| CMD | Hex | Name | Beschreibung |
|-----|-----|------|--------------|
| 144 | `0x90` | HomePage Telemetry | Batterie, Reichweite, Spannung |
| 145 | `0x91` | Realtime Status v0 | Kompakt-Status |
| 146 | `0x92` | DrivePage Telemetry | Speed, Distanz, Trip |

---

## Status-Response (0x70)

37 Bytes. Mapping verifiziert gegen BT-HCI-Capture und offizielle APK (DeviceCarInfo.java, b4/a.java case 112).

**Hinweis:** `data[0]` ist ein Version/Type-Byte. Offizielle APK-Byte-Indizes (Byte 0-38) entsprechen `data[1]`-`data[39]`.

| data[] | Offiziell | Name | Werte | Verifiziert |
|--------|-----------|------|-------|-------------|
| 1 | Byte 0 | Binding Status | `0x00`/`0x01` | APK |
| 2 | Byte 1 | Drive Mode | `0x03`=ECO, `0x05`=SPORT | BT-Capture: 0x58 ändert dieses Byte |
| 3 | Byte 2 | Lock Status | `0x00`=offen, `0x01`=gesperrt | BT-Capture: 0x51 ändert dieses Byte |
| 4 | Byte 3 | CCS (Tempomat) | `0x00`/`0x01` | APK |
| 5 | Byte 4 | Tail Light | `0x00`/`0x01` | APK |
| 6 | Byte 5 | ERS Level | `0x1E`=30, `0x3C`=60, `0x5A`=90 | Live: 0x53 ändert dieses Byte |
| 7 | Byte 6 | Mileage Algorithm | Wert | APK |
| 8 | Byte 7 | Mileage Unit | `0x00`=MPH, `0x01`=KM | APK |
| 9 | Byte 8 | Auto Sensor (Licht) | `0x00`/`0x01` | BT-Capture: 0x57 ändert dieses Byte |
| 10 | Byte 9 | Tyre Switch | `0x00`/`0x01` | APK |
| 11 | Byte 10 | Ambient Light | `0x00`/`0x01` | APK |
| 12 | Byte 11 | TCS Switch | `0x00`/`0x01` | Live: 0x5F ändert dieses Byte |
| 13 | Byte 12 | Turn Sound | `0x00`/`0x01` | Live: 0x60 ändert dieses Byte |
| 14 | Byte 13 | Proximity Key | `0x00`/`0x01` | APK |
| 15 | Byte 14 | Night Mode | `0x00`/`0x01` | APK |
| 16-19 | Byte 15-18 | Light E/D/S, Algo | Werte | APK |
| 20 | Byte 19 | Startup Speed | `0x00`-`0x05` | APK |
| 21 | Byte 20 | Speed Limit | Bit7=aktiv, Bits0-6=km/h | APK |
| 22-25 | Byte 21-24 | Volume, Lang, Logo, DayRun | Werte | APK |
| 26 | Byte 25 | **Max Speed** | z.B. `0x16`=22 km/h | Live: Firmware-Cap, nicht änderbar |
| 27 | Byte 26 | Drive Mode 2 | Wert | APK |
| 28-37 | Byte 27-36 | Charge, Lock, Weather etc. | Werte | APK |

---

## Telemetrie

### HomePage (0x90) — Batterie & Reichweite

Offizielles Parsing aus APK (DeviceHomePageInfo):

| data[] | Offiziell | Name | Format |
|--------|-----------|------|--------|
| 1 | Byte 0 | Warning Code | uint8 |
| 2 | Byte 1 | Driving Mode | uint8 |
| 3 | Byte 2 | **Battery %** | uint8 (0-100) |
| 4 | Byte 3 | Battery Status | uint8 |
| 5 | Byte 4 | Charging State | uint8 |
| 6 | Byte 5 | Lock Push Warn | uint8 |
| 7 | Byte 6 | **Remain Range (km)** | uint8 |
| 8 | Byte 7 | Lock Status | uint8 (Wert - 1) |
| 9-12 | Byte 8-11 | **Battery Voltage (mV)** | uint32 LE |
| 13-16 | Byte 12-15 | Battery Current (mA) | uint32 LE |

### DrivePage (0x92) — Geschwindigkeit & Distanz

Offizielles Parsing aus APK (DeviceSubPageInfo, version=1):

| data[] | Offiziell | Name | Format |
|--------|-----------|------|--------|
| 1 | Byte 0 | Battery % | uint8 |
| 2 | Byte 1 | Driving Status | uint8 |
| 3-4 | Byte 2-3 | **Speed (raw)** | uint16 LE, **/10 für km/h** |
| 5 | Byte 4 | Remain Range (km) | uint8 |
| 6-7 | Byte 5-6 | Trip Distance | uint16 LE |
| 8 | Byte 7 | Trip Duration | uint8 |
| 9-10 | Byte 8-9 | Max Speed | uint16 LE |
| 11-12 | Byte 10-11 | Avg Speed | uint16 LE |
| 13-14 | Byte 12-13 | **Total Mileage** | uint16 LE |
| 15-18 | Byte 14-17 | Total Mileage (4B) | uint32 LE (Override wenn > 0) |

---

## PID (Product ID)

Extraktion aus BLE Scan Record Bytes 6-7 (Little-Endian 16-Bit):

```kotlin
val pid = scanRecord[6].toInt() and 0xFF or
         ((scanRecord[7].toInt() and 0xFF) shl 8)
```

---

## Max-Speed Optionen nach PID

| PID | Verfügbare Geschwindigkeiten (km/h) |
|-----|--------------------------------------|
| 2509 | 25, 30, 35, 40 |
| 2511, 2516 | 25, 32, 45, 50 |
| 2547 | 25, 32, 40, 50, 60 |
| 2585 | 25, 32, 40, 50, 70 |
| 2544 | 25, 30, 35, 40, 45, 50, 55, 60 |
| 2449 | 25, 30, 35, 40, 45, 50, 55, 60, 65 |
| 23452 (ST3 Pro DE) | **22 km/h Firmware-Limit** (nicht änderbar) |

### Firmware-Limit DE

CMD `0x6E` (Max Speed) wird ACK'd, ändert aber auf PID 23452 **nicht** die Höchstgeschwindigkeit. Byte 26 der Status-Response bleibt bei `0x16` (22 km/h).

---

## Licht-Verhalten

Das Lichtsystem des ST3 Pro hat ein besonderes Verhalten, das aus der offiziellen App bestätigt wurde:

### Automatisches Frontlicht (`0x57`)

- **Front- und Rücklicht werden gemeinsam** über den Helligkeitssensor gesteuert
- CMD `0x57` aktiviert/deaktiviert den **automatischen Lichtsensor**
- Bei aktiviertem Sensor schalten sich Front- und Rücklicht je nach Umgebungshelligkeit automatisch ein/aus
- **Wichtig:** Manuelles Ein-/Ausschalten des Frontlichts (z.B. über den physischen Knopf am Scooter) deaktiviert die Automatikfunktion vorübergehend. Sie wird nach einem **Neustart des Scooters** wieder aktiviert.

### Separates Rücklicht (`0x54`)

- CMD `0x54` steuert das Rücklicht separat (falls verfügbar)
- Bei den meisten Firmware-Versionen sind Front- und Rücklicht jedoch gekoppelt

### Blinker-Ton (`0x60`)

- CMD `0x60` steuert **nicht** das Rücklicht, sondern den **akustischen Blinker-Sound**
- Häufiger Fehler: `0x60` wurde in frühen RE-Analysen fälschlich als Taillight identifiziert

---

## DFU-Protokoll (Firmware-Update über BLE)

Das Firmware-Update (Device Firmware Update) nutzt das XMODEM-Protokoll über die gleiche BLE-Characteristic wie normale Kommandos.

### Ablauf

1. **DFU-Modus aktivieren** — Spezieller BLE-Befehl versetzt den Scooter in den Update-Modus
2. **Firmware-Transfer** — Binärdatei wird in 128-Byte-Blöcken via XMODEM übertragen
3. **CRC-16 Prüfsumme** — Jeder Block wird mit CRC-16 verifiziert
4. **Verifikation und Neustart** — Nach vollständiger Übertragung verifiziert der Scooter die Integrität und startet neu

### XMODEM-Details

| Parameter | Wert |
|-----------|------|
| Blockgröße | 128 Bytes |
| Prüfsumme | CRC-16 |
| Characteristic | Gleiche Write-Characteristic wie BLE-Kommandos (`0xb002`) |
| Firmware-Format | Navee-eigener Header (Modell + Version) + ARM Thumb Code |

### Firmware-Header

```
Offset 0x00: Modell-String (z.B. "T22020" für Meter, "T24180" für BMS)
Offset 0x06: Typ-Byte (0x01=Meter, 0x03=BMS)
Offset 0x07: Version-String (z.B. "00030001" für v2.0.3.1)
Offset 0x10: Code-Start-Offset + Größe
Ab ~0x100:   ARM Thumb Maschinencode (Cortex-M, nach FF-Padding)
```

### Verfügbare Firmware-Komponenten

| Komponente | Version | Größe | Typ-Byte |
|-----------|---------|-------|----------|
| **Meter** (Dashboard) | 2.0.3.1 | 138240 Bytes | 0x01 |
| **BMS** (Batterie) | 1.0.0.4 | ~24 KB | 0x03 |

> **Hinweis:** Rollback ist jederzeit möglich durch erneutes Flashen der Original-Firmware. Detaillierte Analyse der Firmware-Inhalte siehe [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md#ghidra-analyse-ergebnisse-detailliert).

---

## Internal UART Protocol

The scooter also uses an internal UART protocol (19200 baud, 8N1) between the dashboard and motor controller. This protocol uses a **different frame format** than BLE (no `55 AA` header, complement header/footer pairs `0x61/0x9E` and `0x64/0x9B`).

> Full documentation: [INTERNAL_UART_PROTOCOL.md](INTERNAL_UART_PROTOCOL.md)

---

## See Also

- [AUTHENTICATION.md](AUTHENTICATION.md) — Auth flow with AES keys and Device-ID
- [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) — Methodology and findings
- [INTERNAL_UART_PROTOCOL.md](INTERNAL_UART_PROTOCOL.md) — Dashboard to controller UART protocol
- [HARDWARE.md](HARDWARE.md) — Wiring, MCU identification, flash layout
- [ATTACK_VECTORS.md](ATTACK_VECTORS.md) — All attempted approaches
