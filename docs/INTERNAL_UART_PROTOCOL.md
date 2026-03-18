# Internes UART-Protokoll — Navee ST3 Pro

Dokumentation des internen UART-Kommunikationsprotokolls zwischen Dashboard und Motor-Controller.

---

## Physische Verbindung

### Kabelbelegung (5 Adern im Kabelbaum Dashboard → Controller)

| Farbe   | Funktion        | Spannung  | Hinweis                        |
|---------|-----------------|-----------|--------------------------------|
| Schwarz | GND             | 0V        | Referenz-Ground                |
| Rot     | VCC (Akku)      | 53.04V    | ⚠️ NICHT mit Elektronik verbinden! |
| Blau    | VCC (Dashboard) | 52.2V     | ⚠️ NICHT mit Elektronik verbinden! |
| Gelb    | Signal (unbekannt) | 3.76V  | Kein UART — unbekanntes Signal |
| Grün    | UART TX (Controller → Dashboard) | 4.12V | **Datenleitung — 19200 Baud** |

### UART-Parameter

| Parameter | Wert    |
|-----------|---------|
| Baudrate  | 19200   |
| Data Bits | 8       |
| Parity    | None    |
| Stop Bits | 1       |
| Logic Level | ~3.3–4V |

---

## Frame-Format

Das interne Protokoll nutzt ein **anderes Frame-Format** als das BLE-Protokoll (kein `55 AA` Header).

```
┌────────┬──────────┬──────────┬────────┐
│ Header │ DATA     │ Checksum │ Footer │
│ 1 Byte │ n Bytes  │ 1 Byte   │ 1 Byte │
└────────┴──────────┴──────────┴────────┘
```

### Header/Footer-Paarung

Header + Footer = 0xFF (Komplement-Paarung):

| Header | Footer | Richtung / Quelle     |
|--------|--------|-----------------------|
| `0x61` | `0x9E` | Dashboard → Controller |
| `0x64` | `0x9B` | Controller → Dashboard |

### Checksum

**Checksum = SUM(alle Bytes vor Checksum) & 0xFF**

Verifiziert mit allen drei Frame-Typen. ✅

---

## Frame-Typen

### Frame A — Dashboard Status (Header `0x61`, CMD `0x30`)

**Länge:** 15 Bytes | **Frequenz:** ~5x pro Sekunde | **Richtung:** Dashboard → Controller

```
61 30 0a [MODE] [LIGHT] [B5] [B6] [B7] [B8] [B9] [B10] [B11] [B12] [CHK] 9e
```

| Byte | Offset | Name      | Werte beobachtet | Beschreibung |
|------|--------|-----------|-----------------|--------------|
| 0    | —      | Header    | `0x61`          | Dashboard-Frame |
| 1    | —      | CMD       | `0x30`          | Status-Kommando |
| 2    | —      | LEN?      | `0x0a` (10)     | Möglicherweise Länge |
| 3    | B3     | **Mode**  | `0x35`=ECO, `0x33`=SPORT | Fahrmodus |
| 4    | B4     | **Light** | `0x04`=AN, `0x00`=AUS | Scheinwerfer |
| 5    | B5     | Unknown   | `0x88` (136)    | Konstant — möglicherweise Bitfield |
| 6    | B6     | **Speed A** | `0x17` (23)    | **Speed-Limit A (manipulierbar!)** |
| 7    | B7     | **Speed B** | `0x16` (22)    | **Speed-Limit B (manipulierbar!)** |
| 8    | B8     | Unknown   | `0x01`          | Konstant |
| 9    | B9     | Unknown   | `0x00`          | Meist 0 |
| 10   | B10    | **Startup Speed** | `0x0A`/`0x00` | Anlaufgeschwindigkeit (10 km/h / 0) |
| 11-12| B11-B12| Padding?  | `0x00 0x00`     | Immer Null |
| 13   | —      | Checksum  | variabel        | SUM(Bytes 0-12) & 0xFF |
| 14   | —      | Footer    | `0x9E`          | Komplement von 0x61 |

#### Beobachtete Varianten

```
ECO, Licht AN:   61 30 0a 35 04 88 17 15 01 00 00 00 00 89 9e
ECO, Licht AUS:  61 30 0a 35 00 88 17 15 01 00 00 00 00 85 9e
SPORT, Licht AN: 61 30 0a 33 04 88 17 15 01 00 00 00 00 87 9e
```

#### Speed-Limits: Bytes 6 und 7 (BESTÄTIGT)

- **Byte 6:** `0x17` = 23 km/h (ECO-Max + Buffer)
- **Byte 7:** `0x16` = 22 km/h (SPORT-Max DE-Version) 
- Diese Bytes sind die **Speed-Limits** die das Dashboard an den Controller sendet
- **BESTÄTIGT:** Arduino MitM kann diese Werte erfolgreich manipulieren
- Modifikation auf `0x1E`/`0x1E` (30/30 km/h) syntaktisch erfolgreich

**Arduino MitM Implementierung verfügbar:** `/reverse-engineering/navee_uart_mitm_nano/`

---

### Frame B — Telemetrie (Header `0x61`, CMD `0x31`)

**Länge:** 14 Bytes | **Frequenz:** ~3x pro Sekunde | **Richtung:** Dashboard → Controller (oder bidirektional)

```
61 31 09 9a 64 cd 80 80 [VAR] 19 00 00 [CHK] 9e
```

| Byte | Name      | Werte beobachtet | Beschreibung |
|------|-----------|-----------------|--------------|
| 0    | Header    | `0x61`          | Dashboard-Frame |
| 1    | CMD       | `0x31`          | Telemetrie-Kommando |
| 2    | LEN?      | `0x09` (9)      | Möglicherweise Länge |
| 3-7  | Static    | `9a 64 cd 80 80` | Konstant |
| 8    | **Variable** | `0x00`–`0x04` | **Ändert sich live!** Vermutlich Sensor/Throttle |
| 9    | Static    | `0x19` (25)     | Konstant — Temperatur? (25°C?) |
| 10-11| Padding   | `0x00 0x00`     | Immer Null |
| 12   | Checksum  | variabel        | SUM(Bytes 0-11) & 0xFF |
| 13   | Footer    | `0x9E`          | Komplement von 0x61 |

#### Variable Byte 8

Bei Licht-AUS fiel Byte 8 auf `0x00`/`0x01` (vorher `0x02`–`0x04`).
Vermutung: Stromverbrauch, PWM-Level, oder Hallsensor-Feedback.

---

### Frame C — Controller Telemetrie (Header `0x64`, CMD `0x26`)

**Länge:** 18 Bytes | **Frequenz:** ~1x pro Sekunde | **Richtung:** Controller → Dashboard

```
64 26 0d 00 00 04 fb 04 fb 00 30 00 22 d5 48 64 68 9b
```

| Byte | Name      | Hex   | Dezimal | Beschreibung |
|------|-----------|-------|---------|--------------|
| 0    | Header    | `0x64`| —       | Controller-Frame |
| 1    | CMD       | `0x26`| —       | Telemetrie-Kommando |
| 2    | LEN?      | `0x0d`| 13      | Möglicherweise Länge |
| 3-4  | Unknown   | `00 00` | 0, 0  | Speed? (0 km/h im Stillstand) |
| 5-6  | Unknown   | `04 fb` | 1275  | **Akku-Spannung?** (÷25 ≈ 51V?) |
| 7-8  | Unknown   | `04 fb` | 1275  | Wiederholung — zweiter Spannungswert? |
| 9    | Unknown   | `0x00`| 0       | Flags? |
| 10   | Unknown   | `0x30`| 48      | **Max Speed?** (48 ÷ 2 = 24?) |
| 11   | Unknown   | `0x00`| 0       | — |
| 12   | Unknown   | `0x22`| 34      | **Speed Limit?** (`0x22` hex = 22 km/h?) |
| 13-14| Unknown   | `d5 48` | —     | Odometer? Hash? |
| 15   | Unknown   | `0x64`| 100     | **Akku %?** (100% = voll?) |
| 16   | Checksum  | `0x68`| —       | SUM(Bytes 0-15) & 0xFF ✅ |
| 17   | Footer    | `0x9B`| —       | Komplement von 0x64 |

#### Identifizierte Werte

- **Byte 10:** Geschwindigkeitsindikator (62 = Stillstand, 65+ = Bewegung)
- **Byte 12:** `0x22` = Status/Flags  
- **Byte 15:** `0x64` = 100% Akkuladung (bestätigt)

**Frame C blieb bei Modus- und Lichtwechsel komplett unverändert!**
→ Die Werte in Frame C werden vermutlich nur bei Fahrt aktualisiert.

---

### Sonder-Frame — Moduswechsel-Bestätigung (Header `0x64`, CMD `0x23`)

Einmalig beobachtet beim Moduswechsel:

```
64 23 07 31 30 30 34 19 0a 18 8e 9b
```

| Byte | Hex | ASCII | Beschreibung |
|------|-----|-------|--------------|
| 3-6  | `31 30 30 34` | "1004" | Firmware-Version oder Parameter? |
| 7    | `0x19` | — | 25 dez — Temperatur? |

---

## Zusammenfassung der identifizierten Bytes

### Frame A — Steuerbare Werte

| Byte | Funktion | ECO+Licht | SPORT+Licht | ECO-Licht | Differenz |
|------|----------|-----------|-------------|-----------|-----------|
| 3    | Mode     | `0x35`    | `0x33`      | `0x35`    | Mode-Wechsel |
| 4    | Light    | `0x04`    | `0x04`      | `0x00`    | Licht-Toggle |

### Frame C — Mögliche Speed-Werte (noch zu verifizieren)

| Byte | Wert  | Hypothese |
|------|-------|-----------|
| 10   | `0x30` (48) | Max Speed × 2? |
| 12   | `0x22` (34) | Speed Limit (BCD: "22" km/h?) |
| 15   | `0x64` (100) | Akku-Prozent |

---

## Nächste Schritte

### Phase 1 — Weitere Byte-Identifikation  
- [x] **Byte 10 in Frame A** = Anlaufgeschwindigkeit (0x0A = 10 km/h, 0x00 = keine)
- [ ] Tempomat ein/aus togglen → welches Byte ändert sich?
- [ ] Roller fahren → Frame C Bytes beobachten (Speed, Distanz)
- [ ] Bremse betätigen → neuer Frame-Typ?

### Phase 2 — Arduino/ESP32 MitM (ERFOLGREICH IMPLEMENTIERT)
- [x] Arduino Nano zwischen Dashboard (Grün) und Controller geklemmt
- [x] Frame A abgefangen und Byte 6/7 manipuliert (Speed-Limits erhöht)
- [x] Checksum neu berechnet und Frame weitergeleitet
- [x] ~2000+ Frames erfolgreich modifiziert
- [x] Serial-Interface mit Befehlen (u=Unlock, p=Passthrough, +/- für Speed)

### Phase 3 — Speed Unlock Status
1. **Byte 6/7 in Frame A erhöhen** ✅ IMPLEMENTIERT — Dashboard Speed-Limits werden manipuliert
2. **Anlaufgeschwindigkeit (Byte 10)** ✅ KANN auf 0x00 gesetzt werden  
3. **Realer Fahrtest** ❌ **ERFOLGLOS** — Controller ignoriert UART-Manipulation komplett

#### Testergebnis

**Getestet:** Über 1000 Frames erfolgreich von 24/22 auf 30/30 km/h manipuliert
**Ergebnis:** Controller bleibt bei 22 km/h — **UART-Limits werden ignoriert**
**Fazit:** Speed-Limits sind firmware-seitig im Controller hardcoded (PID 23452)

---

## Benötigte Hardware

| Gerät | Zweck |
|-------|-------|
| USB-UART-Adapter (CP2102, FT232RL, CH340) | UART-Debugging und Protokoll-Analyse |
| Multimeter | Spannungsmessung der Signalleitungen |
| Feine Messleitungen/Dupont-Kabel | Präzise Verbindungen zu Signalleitungen |
| Arduino Nano oder ESP32 DevKit | MitM-Controller für Speed-Manipulation |
| Lötzinn (0.5-0.8mm) | Permanente Installationen |
| Schrumpfschlauch | Isolierung der Verbindungen |
| Logic Level Shifter | Falls 5V ↔ 3.3V Anpassung nötig |

---

© 2026 Martin Pfeffer
