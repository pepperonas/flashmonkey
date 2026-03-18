# UART Man-in-the-Middle Speed Unlock Guide

> ⚠️ **WICHTIGER HINWEIS - METHODE ERFOLGLOS**  
> Diese Methode wurde implementiert und getestet, ist aber **nicht wirksam**. Der Controller ignoriert UART-Speed-Limits komplett und bleibt bei 22 km/h. Diese Dokumentation verbleibt zur Referenz und um anderen die gleiche erfolglose Arbeit zu ersparen.

## Übersicht

Diese Anleitung beschreibt eine **gescheiterte** Methode zur Speed-Unlock des Navee ST3 Pro (DE-Version) mittels UART Man-in-the-Middle.

**Status:** ❌ **Funktional implementiert, aber unwirksam** ❌

---

## Hintergrund

### Das Problem
- Die deutsche Version (PID 23452) hat ein firmware-seitiges 22 km/h Limit
- BLE-Commands zum Ändern der Geschwindigkeit werden ignoriert  
- Das alte "weißes Kabel durchschneiden" funktioniert nicht mehr

### Die Lösung
Das Dashboard sendet über UART kontinuierlich Speed-Limits an den Controller (Frame A, Bytes 6-7). Ein Arduino zwischen Dashboard und Controller kann diese Werte abfangen und erhöhen.

---

## Benötigte Hardware

- **Arduino Nano** (ATmega328P) oder kompatibel
- **USB-Kabel** für Arduino (Stromversorgung + Serial Monitor)
- **Dupont-Kabel** oder dünne Litze
- **Lötkolben** (optional, für permanente Installation)
- **Multimeter** (zum Verifizieren der Spannungen)

⚠️ **WARNUNG:** Niemals die roten (53V) oder blauen (52V) Kabel anfassen!

---

## Verkabelung

### Schritt 1: Dashboard-Kabelbaum lokalisieren

Der 5-adrige Stecker zwischen Dashboard und Controller:
- **Schwarz:** GND (0V)
- **Rot:** Akku VCC (53V) ⚠️ NICHT ANFASSEN
- **Blau:** Dashboard VCC (52V) ⚠️ NICHT ANFASSEN  
- **Gelb:** Unbekanntes Signal (3.76V)
- **Grün:** UART TX (4.12V) ← **DIESE ADER TRENNEN**

### Schritt 2: Grüne Ader durchtrennen

1. Scooter ausschalten und Akku abstecken (falls möglich)
2. Grüne Ader vorsichtig durchtrennen
3. Beide Enden abisolieren (ca. 5mm)

### Schritt 3: Arduino anschließen

```
Dashboard-Ende (grün) ──→ Arduino Pin D2 (SoftSerial RX)
Arduino Pin D3 (SoftSerial TX) ──→ Controller-Ende (grün)
Scooter GND (schwarz) ──→ Arduino GND
Arduino USB ──→ Computer
```

### Verbindungsdiagramm

```
┌─────────────┐      Grüne Ader      ┌──────────────┐
│  Dashboard  │────X────┬────────────│  Controller  │
└─────────────┘         │            └──────────────┘
                        │
                   ┌────▼────┐
                   │ Arduino │
                   │  Nano   │
                   │         │
                   │ D2   D3 │
                   │ GND USB │
                   └──┬───┬──┘
                      │   │
                 Schwarz  Computer
                  (GND)
```

---

## Software Installation

### Schritt 1: Arduino IDE vorbereiten

1. Arduino IDE installieren (https://www.arduino.cc/en/software)
2. Board: Tools → Board → Arduino Nano
3. Prozessor: Tools → Processor → ATmega328P (Old Bootloader)
4. Port: Tools → Port → /dev/cu.usbserial-xxx (Mac) oder COMx (Windows)

### Schritt 2: Code flashen

1. Datei öffnen: `/reverse-engineering/navee_uart_mitm_nano/navee_uart_mitm_nano.ino`
2. Upload-Button klicken (→)
3. Warten bis "Done uploading" erscheint

### Schritt 3: Serial Monitor öffnen

1. Tools → Serial Monitor
2. Baudrate: 115200 
3. Line Ending: Newline

---

## Bedienung

### Serial Monitor Befehle

| Befehl | Funktion | Beschreibung |
|--------|----------|--------------|
| **p** | Passthrough | Normale Weiterleitung ohne Manipulation (Standard) |
| **u** | Unlock | Speed-Limits auf 30/30 km/h erhöhen |
| **l** | Lock | Original Speed-Limits (22 km/h) |
| **s** | Status | Zeigt aktuelle Einstellungen und Statistiken |
| **+** | Speed +1 | Ziel-Geschwindigkeit erhöhen |
| **-** | Speed -1 | Ziel-Geschwindigkeit verringern |

### Typische Ausgabe

```
================================
 NAVEE ST3 Pro UART MitM
 Arduino Nano Edition
================================
[OK] Passthrough-Modus aktiv
[OK] Warte auf UART-Daten...

[A] SPT L:ON SA:23 SB:22
[C] B10:62 B12:0x22 B15:100%
[STAT] A:195 B:99 C:21 MOD:0 passthrough
```

Nach Unlock ('u'):
```
[MODE] UNLOCKED! A=30 B=30
[A] SPT L:ON SA:23 SB:22 ->30/30
[STAT] A:488 B:247 C:52 MOD:418 UNLOCKED
```

### Frame-Erklärung

- **[A]** Frame A vom Dashboard (Speed-Limits)
  - SA/SB = Speed A/B (Original-Werte)
  - ->30/30 = Modifizierte Werte
- **[C]** Frame C vom Controller (Telemetrie)
  - B10 = Geschwindigkeitsindikator
  - B15 = Akku-Prozent
- **[STAT]** Statistik
  - A/B/C = Frame-Counter
  - MOD = Anzahl modifizierter Frames

---

## Test-Prozedur

### Aufgebockter Test

1. Hinterrad aufbocken
2. Scooter einschalten
3. Serial Monitor beobachten (Frames sollten durchlaufen)
4. 'u' für Unlock eingeben
5. MOD-Counter sollte steigen
6. Rad von Hand drehen + Gas geben

### Realer Fahrtest

⚠️ **NUR AUF PRIVATGELÄNDE!**

1. Passthrough-Modus ('p') aktivieren
2. Normale Fahrt bis 22 km/h → Geschwindigkeit notieren
3. Anhalten, Unlock ('u') aktivieren  
4. Erneut fahren → Über 22 km/h beschleunigen?

---

## Fehlerbehebung

### Keine Frames im Serial Monitor

- GND-Verbindung prüfen
- Grüne Ader wirklich durchtrennt?
- D2/D3 vertauscht?
- Scooter eingeschaltet?

### Arduino resettet sich

- Stromversorgung instabil
- Masse-Problem
- Eventuell Kondensator zwischen VCC und GND

### MOD-Counter steigt, aber keine Wirkung

- Controller ignoriert möglicherweise die Manipulation
- Andere Bytes müssen eventuell auch angepasst werden
- Realer Fahrtest nötig (aufgebockt ≠ real)

---

## Technische Details

### Frame A Manipulation

```c
// Original vom Dashboard
Frame A: 61 30 0A 33 04 88 [17] [16] 01 00 00 00 00 [CHK] 9E
                              ^    ^
                           23km/h 22km/h

// Nach Manipulation  
Frame A: 61 30 0A 33 04 88 [1E] [1E] 01 00 00 00 00 [CHK] 9E
                              ^    ^
                           30km/h 30km/h
```

### Checksum-Berechnung

```c
uint8_t calcChecksum(uint8_t* data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) {
    sum += data[i];
  }
  return sum;
}
```

---

## Sicherheitshinweise

⚠️ **Elektrische Sicherheit**
- NIEMALS Rot (53V) oder Blau (52V) berühren
- Nur bei ausgeschaltetem Scooter verkabeln
- Isolierte Werkzeuge verwenden

⚠️ **Rechtliche Hinweise**
- Modifikationen nur auf Privatgelände testen
- Im öffentlichen Verkehr gelten gesetzliche Limits (20 km/h in DE)
- Versicherungsschutz kann erlöschen

⚠️ **Hardware-Risiken**
- Falsche Verkabelung kann Controller beschädigen
- Keine Garantie für Funktionsfähigkeit
- Auf eigene Gefahr

---

## Weiterführende Entwicklung

### Geplante Verbesserungen

- [ ] ESP32 mit Bluetooth für kabellose Steuerung
- [ ] Permanente Installation mit Schalter
- [ ] Automatische Geschwindigkeitsanpassung
- [ ] OTA-Updates für Arduino

### Alternative Ansätze

1. **Controller-Firmware**: JTAG/SWD-Zugang zum STM32
2. **Hardware-Mod**: Shunt-Widerstand modifizieren
3. **Dashboard-Tausch**: Internationale Version einbauen

---

## Credits

- **Entwicklung:** Martin Pfeffer
- **Implementierung:** Arduino Nano MitM

---

## Changelog

- **v1.0**: Erste funktionierende Version
- Speed-Limit Manipulation implementiert
- Anlaufgeschwindigkeits-Bypass hinzugefügt
- Serial-Interface mit Befehlen

---

© 2026 Martin Pfeffer | MIT License