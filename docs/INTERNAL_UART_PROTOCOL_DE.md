[English](INTERNAL_UART_PROTOCOL.md) | [Deutsch](INTERNAL_UART_PROTOCOL_DE.md)

# Internes UART-Protokoll — Dashboard ↔ Controller

Dokumentation des internen UART-Kommunikationsprotokolls zwischen dem Navee ST3 Pro Dashboard (RTL8762C) und dem Motorcontroller.

---

## Physikalische Schicht

### 5-adriger Dashboard-Kabel-Pinout

| Farbe | Funktion | Spannung | Hinweise |
|-------|----------|----------|----------|
| Schwarz | GND | 0 V | Bezugsmasse |
| Rot | VCC (Akku) | 53,04 V | WARNUNG: NICHT an Mikrocontroller anschließen |
| Blau | VCC (Dashboard) | 52,2 V | WARNUNG: NICHT an Mikrocontroller anschließen |
| Gelb | Controller RX | 3,8 V | Dashboard → Controller Dateneingang (bestätigt) |
| Grün | Controller TX | ~4,12 V | Controller → Dashboard Datenausgang |

### UART-Parameter

| Parameter | Wert |
|-----------|------|
| Baudrate | 19200 |
| Datenbits | 8 |
| Parität | Keine |
| Stoppbits | 1 |
| Logikpegel | ~4 V (nicht standardmäßig — weder 3,3 V noch 5 V) |

Der Logikpegel von ca. 4 V bedeutet, dass für eine direkte Verbindung zu einem 3,3-V-Mikrocontroller (Arduino, ESP32) ein Logikpegelwandler erforderlich ist. In der Praxis haben 5-V-Arduino-Eingänge dieses Signal bei Tests direkt toleriert, für sicheren Langzeitbetrieb wird jedoch ein Pegelwandler empfohlen.

---

## Frame-Format

Das interne UART-Protokoll verwendet eine andere Frame-Struktur als das BLE-Protokoll. Es gibt keinen `0x55 0xAA`-Header. Stattdessen werden komplementäre Header/Footer-Byte-Paare verwendet.

```
┌──────────┬──────────────┬──────────┬──────────┐
│ Header   │ DATEN        │ Prüfsumme│ Footer   │
│ 1 Byte   │ n Bytes      │ 1 Byte   │ 1 Byte   │
└──────────┴──────────────┴──────────┴──────────┘
```

### Header/Footer-Komplementpaare

Header und Footer sind stets Komplemente: `Header XOR Footer = 0xFF`.

| Richtung | Header | Footer | Komplementprüfung |
|----------|--------|--------|-------------------|
| Dashboard → Controller | `0x61` | `0x9E` | `0x61 + 0x9E = 0xFF` ✅ |
| Controller → Dashboard | `0x64` | `0x9B` | `0x64 + 0x9B = 0xFF` ✅ |

### Prüfsummenberechnung

```
Prüfsumme = SUM(alle Bytes vor der Prüfsummenposition) & 0xFF
```

Dies schließt das Header-Byte bis zum letzten Datenbyte ein. Verifiziert gegen alle drei Frame-Typen. ✅

---

## Frame-Typen

### Frame A — Dashboard-Status (Dashboard → Controller)

**Länge:** 15 Bytes | **Frequenz:** ~5-mal pro Sekunde | **Richtung:** Dashboard → Controller

```
61 30 0A [MODE] [LIGHT] [B5] [SPD_A] [SPD_B] [B8] [B9] [STARTUP] [B11] [B12] [CHK] 9E
```

| Offset | Feld | Beobachtete Werte | Verifiziert |
|--------|------|-------------------|-------------|
| 0 | Header | `0x61` | ✅ |
| 1 | Befehl | `0x30` | ✅ |
| 2 | Datenlänge | `0x0A` (10) | ✅ |
| 3 | Fahrmodus | `0x35` = ECO, `0x33` = SPORT | ✅ Live verifiziert |
| 4 | Frontlicht | `0x04` = AN, `0x00` = AUS | ✅ Live verifiziert |
| 5 | Unbekannt | `0x88` (136) — konstant | Möglicherweise Bitfeld |
| 6 | Geschwindigkeitswert A | `0x17` (23) typisch | Beobachtet |
| 7 | Geschwindigkeitswert B | `0x16` (22) typisch | Beobachtet |
| 8 | Unbekannt | `0x01` — konstant | |
| 9 | Unbekannt | `0x00` — meist null | |
| 10 | Anlaufgeschwindigkeit | `0x0A` (10 km/h) oder `0x00` | Identifiziert |
| 11–12 | Padding | `0x00 0x00` — immer null | |
| 13 | Prüfsumme | SUM(Bytes 0–12) & 0xFF | ✅ |
| 14 | Footer | `0x9E` | ✅ |

#### Beobachtete Frame-Varianten

```
ECO,   Licht AN:  61 30 0A 35 04 88 17 15 01 00 00 00 00 89 9E
ECO,   Licht AUS: 61 30 0A 35 00 88 17 15 01 00 00 00 00 85 9E
SPORT, Licht AN:  61 30 0A 33 04 88 17 15 01 00 00 00 00 87 9E
```

#### Geschwindigkeits-Bytes 6 und 7 — Wichtige Erkenntnis

Diese Bytes wurden zunächst als Geschwindigkeitslimit-Steuerwerte identifiziert, die vom Dashboard an den Controller gesendet werden. Arduino-MitM-Tests (1000+ Frames von `0x17`/`0x16` auf `0x1E`/`0x1E`, d. h. 30/30 km/h, geändert) zeigten, dass der Controller diese Werte vollständig ignoriert. Der Scooter blieb während des gesamten Tests bei 22 km/h.

**Fazit:** Bytes 6 und 7 sind Telemetrie- oder Anzeigewerte, keine autoritative Geschwindigkeitslimit-Steuerung. Siehe den Abschnitt zur Geschwindigkeitslimit-Architektur weiter unten.

#### Anlaufgeschwindigkeit — Byte 10

- `0x0A` (10): Rollstart-Unterstützungsgeschwindigkeit von 10 km/h
- `0x00` (0): Keine Anlaufunterstützung

---

### Frame B — Dashboard-Telemetrie (Dashboard → Controller)

**Länge:** 14 Bytes | **Frequenz:** ~3-mal pro Sekunde | **Richtung:** Dashboard → Controller

```
61 31 09 9A 64 CD 80 80 [VAR] 19 00 00 [CHK] 9E
```

| Offset | Feld | Beobachtete Werte | Hinweise |
|--------|------|-------------------|----------|
| 0 | Header | `0x61` | |
| 1 | Befehl | `0x31` | |
| 2 | Datenlänge | `0x09` (9) | |
| 3–7 | Statisch | `9A 64 CD 80 80` | Konstant über alle beobachteten Frames |
| 8 | Variabel | `0x00`–`0x04` | Ändert sich im Betrieb — siehe Hinweis unten |
| 9 | Statisch | `0x19` (25) | Möglicherweise Temperatur in °C (25 °C Umgebung) |
| 10–11 | Padding | `0x00 0x00` | Immer null |
| 12 | Prüfsumme | SUM(Bytes 0–11) & 0xFF | |
| 13 | Footer | `0x9E` | |

#### Variables Byte 8

Byte 8 wurde beobachtet, auf `0x00`/`0x01` zu fallen, wenn das Frontlicht ausgeschaltet wurde (zuvor `0x02`–`0x04` bei eingeschaltetem Licht). Wahrscheinliche Kandidaten: Leistungsaufnahmepegel, PWM-Tastgrad oder Hall-Sensor-Rückmeldung vom Motor.

---

### Frame C — Controller-Telemetrie (Controller → Dashboard)

**Länge:** 18 Bytes | **Frequenz:** ~1-mal pro Sekunde | **Richtung:** Controller → Dashboard

```
64 26 0D 00 00 04 FB 04 FB 00 30 00 22 D5 48 64 68 9B
```

| Offset | Feld | Hex | Dezimal | Hinweise |
|--------|------|-----|---------|----------|
| 0 | Header | `0x64` | — | Controller-Frame |
| 1 | Befehl | `0x26` | — | |
| 2 | Datenlänge | `0x0D` | 13 | |
| 3–4 | Unbekannt | `00 00` | 0, 0 | Möglicherweise aktuelle Geschwindigkeit (0 = stehend) |
| 5–6 | Unbekannt | `04 FB` | 1275 | Möglicherweise Akkuspannung (1275 ÷ 25 ≈ 51 V) |
| 7–8 | Unbekannt | `04 FB` | 1275 | Wiederholter Spannungswert oder zweite Messung |
| 9 | Unbekannt | `0x00` | 0 | Status-Flags? |
| 10 | Unbekannt | `0x30` | 48 | Geschwindigkeitsindikator (62 = stehend, 65+ = fahrend); 48 ÷ 2 = 24? |
| 11 | Unbekannt | `0x00` | 0 | |
| 12 | Unbekannt | `0x22` | 34 | Möglicherweise Geschwindigkeitslimit (0x22 hex = 22 dezimal = 22 km/h?) |
| 13–14 | Unbekannt | `D5 48` | — | Möglicherweise Kilometerzähler oder Hash |
| 15 | Unbekannt | `0x64` | 100 | Akkustand in Prozent (100 % = voll) ✅ |
| 16 | Prüfsumme | `0x68` | — | SUM(Bytes 0–15) & 0xFF ✅ |
| 17 | Footer | `0x9B` | — | |

Frame C wurde beobachtet, bei Moduswechseln (ECO ↔ SPORT) und Lichtschaltvorgängen völlig unverändert zu bleiben. Werte in Frame C werden wahrscheinlich nur während aktiver Fahrt aktualisiert.

---

### Sonder-Frame — Moduswechsel-Bestätigung (Controller → Dashboard)

Einmalig bei einem Fahrmodus-Wechsel beobachtet. CMD `0x23`, 12 Bytes gesamt.

```
64 23 07 31 30 30 34 19 0A 18 8E 9B
```

| Offset | Hex | ASCII | Hinweise |
|--------|-----|-------|----------|
| 0 | `0x64` | — | Controller-Header |
| 1 | `0x23` | — | Befehl — Moduswechsel-Bestätigung |
| 2 | `0x07` | — | Datenlänge (7) |
| 3–6 | `31 30 30 34` | "1004" | Firmware-Versions-String oder Parametersatz |
| 7 | `0x19` | — | 25 dezimal — möglicherweise Temperatur in °C |
| 8–9 | `0x0A 0x18` | — | Unbekannt |
| 10 | `0x8E` | — | Prüfsumme |
| 11 | `0x9B` | — | Footer |

Dieser Frame wurde nur einmalig beobachtet und wird möglicherweise vom Controller gesendet, um den Empfang eines Moduswechsel-Befehls aus Frame A zu bestätigen.

---

## Schlüsselerkenntnis: Geschwindigkeitslimit-Architektur

Das UART-MitM-Experiment (Arduino UNO auf der grünen Ader eingesetzt) bewies schlüssig, dass das Geschwindigkeitslimit nicht durch UART-Frame-Manipulation änderbar ist.

### Versuchsaufbau

- Arduino Nano zwischen Dashboard-Stecker (grüne Ader) und Controller eingesetzt
- Frame-A-Bytes 6 und 7 abgefangen und von `0x17`/`0x16` auf `0x1E`/`0x1E` (30/30 km/h) umgeschrieben
- Prüfsumme für jeden modifizierten Frame korrekt neu berechnet
- Über 1168 Frames erfolgreich abgefangen, modifiziert und weitergeleitet
- Serielle Schnittstelle ermöglichte Live-Steuerung: `u` = entsperren, `p` = Durchleitung, `+`/`-` für Geschwindigkeitsanpassung

### Ergebnis

Der Scooter blieb während des gesamten Tests bei 22 km/h. Der Controller reagierte nicht auf die modifizierten Werte.

### Fazit

```
Geschwindigkeitslimit-Kette (Normalbetrieb):
  Dashboard FW (RTL8762C)
    → berechnet Geschwindigkeitslimit basierend auf PID / Ländercode
    → sendet UART-Frames an Controller
    → Controller setzt Limit aus eigenem internen Zustand durch

MitM-Angriff (getestet):
  Dashboard → [Arduino modifiziert Frame-A-Bytes 6-7] → Controller
    → Controller IGNORIERT die manipulierten Geschwindigkeitswerte
    → Geschwindigkeit bleibt bei 22 km/h
```

Das Geschwindigkeitslimit wird innerhalb der Controller-Firmware durchgesetzt, nicht durch den UART-Datenstrom. Die Dashboard-UART-Frames spiegeln das konfigurierte Limit als Telemetrie wider, aber der Controller verwendet diese Werte nicht als maßgebliche Quelle. Das Limit muss auf Firmware-Ebene adressiert werden (RTL8762C-Patch bei Offset `0xF848`).

---

## Übersicht identifizierter Bytes

### Frame A — Bestätigte Felder

| Offset | Funktion | ECO + Licht AN | SPORT + Licht AN | ECO + Licht AUS | Änderungsauslöser |
|--------|----------|----------------|------------------|-----------------|-------------------|
| 3 | Fahrmodus | `0x35` | `0x33` | `0x35` | Modus-Taste |
| 4 | Frontlicht | `0x04` | `0x04` | `0x00` | Licht-Taste |
| 10 | Anlaufgeschwindigkeit | `0x0A` | — | `0x00` | Unbekannt |

### Frame C — Kandidatenfelder (nicht vollständig verifiziert)

| Offset | Wert | Hypothese |
|--------|------|-----------|
| 10 | `0x30` (48) | Geschwindigkeitsindikator (48 ÷ 2 = 24?) oder roher Zähler |
| 12 | `0x22` (34) | Geschwindigkeitslimit in km/h (0x22 dezimal = 34, aber Hex-Ziffern „22" = 22 km/h) |
| 15 | `0x64` (100) | Akkustand in Prozent — bestätigt bei Vollladung |

---

## Benötigte Hardware

| Gerät | Zweck |
|-------|-------|
| USB-UART-Adapter (CP2102, FT232RL, CH340) | UART-Debugging und Protokoll-Mitschnitt |
| Multimeter | Spannungsmessung an Signalleitungen |
| Feine Messspitzen / Dupont-Kabel | Präzise Verbindungen zu Signalleitungen |
| Arduino Nano oder ESP32 DevKit | MitM-Controller für Frame-Abfangversuche |
| Logikpegelwandler (3,3 V ↔ 5 V) | Erforderlich wenn Mikrocontroller nicht 5-V-tolerant |
| Lötzinn (0,5–0,8 mm) | Dauerhafte Installationen |
| Schrumpfschlauch | Isolierung für Lötstellen |

---

## Offene Fragen

Die folgenden Felder wurden noch nicht eindeutig identifiziert und erfordern weitere Untersuchung:

- Byte 5 in Frame A (`0x88`) — konstanter Wert, möglicherweise ein Bitfeld für zusätzliche Flags
- Variables Byte 8 in Frame B — bestätigen ob es mit der Gasgriff-Position oder dem Leistungsbedarf korreliert
- Bytes 3–4 in Frame C — bestätigen ob sie die aktuelle Geschwindigkeit während der Fahrt kodieren
- Bytes 5–8 in Frame C — Akkuspannungs-Hypothese durch Messung bei verschiedenen Ladezuständen bestätigen
- Byte 10 in Frame C — während der Fahrt beobachten um festzustellen ob es die Geschwindigkeit verfolgt
- Bytes 13–14 in Frame C (`D5 48`) — nach Fahrten auf Änderungen prüfen; könnte Kilometerzähler sein

---

*Referenzimplementierung: `/reverse-engineering/navee_uart_mitm_nano/`*

*© 2026 Martin Pfeffer*
