# SWD/JTAG Direct Flash — Navee ST3 Pro Meter-MCU

Anleitung zum direkten Flashen der Meter-Firmware über die SWD-Debug-Schnittstelle.

**Warum SWD?** Der OTA-Bootloader hat eine Integritätsprüfung die jede modifizierte Firmware ablehnt (verifiziert mit 7 verschiedenen Binaries, davon 2× Original erfolgreich). Die Checksumme ist intern im Bootloader gespeichert und kann nicht über OTA umgangen werden. SWD umgeht den Bootloader komplett.

---

## Hardware

### Benötigte Teile

| Teil | Preis | Bezugsquelle |
|------|-------|--------------|
| ST-Link V2 (oder Clone) | ~5€ | Amazon, AliExpress |
| Dupont-Kabel (Female-Female) | ~2€ | Amazon |
| Multimeter | vorhanden | - |
| Lötkolben + Lötzinn (optional) | vorhanden | - |

**Alternativ:** J-Link EDU Mini (~20€) oder CMSIS-DAP Adapter.

### Pinout (3 Verbindungen nötig)

| Signal | ST-Link Pin | Meter-PCB | Beschreibung |
|--------|-------------|-----------|--------------|
| SWDIO | Pin 7 (oder beschriftet) | TBD | Daten (bidirektional) |
| SWCLK | Pin 9 (oder beschriftet) | TBD | Takt |
| GND | Pin 20 (oder beschriftet) | TBD | Masse |

> **WICHTIG:** Die SWD-Pads auf dem Meter-PCB müssen noch identifiziert werden!
> Typisch sind beschriftete Test-Pads (CLK, DIO, RST, GND) oder ein
> unbelegter 4/5-Pin Header auf dem Board.

### SWD-Pads finden

1. Scooter ausschalten und Akku abklemmen
2. Dashboard-Gehäuse öffnen (Schrauben an der Unterseite)
3. Meter-PCB freilegen
4. Suche nach:
   - Unbelegtem Pin-Header (4-5 Pins in Reihe)
   - Beschriftete Test-Pads: `CLK`, `DIO`, `SWD`, `RST`, `GND`, `3V3`
   - Runde Lötpads mit Beschriftung
5. Fotos machen und MCU-Bezeichnung notieren (z.B. "STM32F103", "GD32F303", etc.)

### MCU identifizieren

Die MCU-Bezeichnung auf dem Chip bestimmt:
- Flash-Größe und -Adresse
- SWD-Geschwindigkeit
- OpenOCD Target-Konfiguration

Häufige MCUs in E-Scooter-Dashboards:
| MCU | Flash | SRAM | Hinweis |
|-----|-------|------|---------|
| STM32F103C8 | 64KB @ 0x08000000 | 20KB | "Blue Pill" |
| STM32F103CB | 128KB @ 0x08000000 | 20KB | Medium-density |
| STM32F103RB | 128KB @ 0x08000000 | 20KB | 64-Pin |
| GD32F103xx | 64-128KB @ 0x08000000 | 20KB | STM32-Clone |
| GD32F303xx | 256KB @ 0x08000000 | 48KB | Enhanced |
| MM32F103xx | 128KB @ 0x08000000 | 20KB | MindMotion Clone |

> **Hinweis:** Die Firmware-Datei ist 138240 Bytes (~135 KB). Das erfordert
> mindestens 256KB Flash — oder die Firmware wird komprimiert/ohne Bootloader
> gespeichert. Die MCU-Bezeichnung klärt das.

---

## Software

### Installation

```bash
# macOS
brew install open-ocd

# Linux
sudo apt install openocd

# Verifizieren
openocd --version
```

### OpenOCD Konfiguration

Erstelle `tools/openocd_meter.cfg`:

```tcl
# ST-Link V2 Interface
source [find interface/stlink.cfg]

# Transport: SWD (nicht JTAG)
transport select hla_swd

# Target MCU — ANPASSEN nach MCU-Identifikation!
# Für STM32F1xx:
source [find target/stm32f1x.cfg]

# Für GD32F1xx (STM32-kompatibel):
# source [find target/stm32f1x.cfg]

# SWD Geschwindigkeit (1000 kHz ist sicher)
adapter speed 1000
```

---

## Ablauf

### Schritt 1: Verbindung testen

```bash
# Scooter AUS, nur SWD-Kabel angeschlossen
# ST-Link an USB, dann:
openocd -f tools/openocd_meter.cfg
```

Erwartete Ausgabe:
```
Info : STLINK V2J37S7 (API v2) VID:PID 0483:3748
Info : Target voltage: 3.3V
Info : stm32f1x.cpu: hardware has 6 breakpoints, 4 watchpoints
Info : Listening on port 3333 for gdb connections
```

Falls "Error: init mode failed" → Pinout prüfen, GND sicherstellen.

### Schritt 2: Flash auslesen (BACKUP!)

```bash
# In einem zweiten Terminal (OpenOCD läuft noch):
telnet localhost 4444

# Flash-Größe ermitteln
> flash info 0

# GESAMTEN Flash dumpen (Backup!)
> flash read_image backup_meter_full.bin 0x08000000

# Oder mit openocd direkt:
openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash read_image tools/firmware/backup_meter_FULL.bin 0x08000000" \
  -c "shutdown"
```

> **KRITISCH:** Das Backup enthält BOOTLOADER + APPLICATION.
> Ohne Backup kein Recovery bei Problemen!

### Schritt 3: Backup verifizieren

```bash
python3 -c "
import hashlib
data = open('tools/firmware/backup_meter_FULL.bin', 'rb').read()
print(f'Backup-Größe: {len(data)} Bytes ({len(data)/1024:.0f} KB)')
print(f'SHA-256: {hashlib.sha256(data).hexdigest()}')
print(f'Erste 16 Bytes: {data[:16].hex()}')

# Vergleiche mit unserer heruntergeladenen Firmware
orig = open('tools/firmware/navee_meter_v2.0.3.1_ORIGINAL.bin', 'rb').read()
# Die heruntergeladene FW hat 16 Bytes Header
# Im Flash steht die FW ab einem bestimmten Offset (nach dem Bootloader)
# Suche die Original-FW im Backup
idx = data.find(orig[16:16+64])
if idx >= 0:
    print(f'Original-FW Code im Backup gefunden bei Offset 0x{idx:04X}')
    print(f'  → Bootloader-Größe: {idx} Bytes ({idx/1024:.0f} KB)')
    print(f'  → Application Start: 0x{0x08000000 + idx:08X}')
else:
    print('Original-FW nicht im Backup gefunden')
    print('Manuell vergleichen oder MCU-Datenblatt konsultieren')
"
```

Aus dem Backup ergibt sich:
- **Bootloader-Größe** (Offset wo die Application beginnt)
- **Application Base-Adresse** (z.B. 0x08004000, 0x08008000)
- Ob die Firmware mit oder ohne Header gespeichert ist

### Schritt 4: Gepatchte Firmware flashen

```bash
# VARIANTE A: Nur den Application-Bereich überschreiben
# (Bootloader bleibt intakt → Recovery über OTA möglich!)
# APP_START = Adresse aus Schritt 3 (z.B. 0x08008000)

openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash write_image erase tools/firmware/navee_meter_v2.0.3.1_PATCHED.bin APP_START" \
  -c "reset run" \
  -c "shutdown"

# VARIANTE B: Nur den Patch schreiben (1 Word an einer Adresse)
# Offset 0xF848 im File → Flash-Adresse = APP_START + 0xF848 - 16
# (Falls die 16-Byte Header nicht im Flash stehen)

openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash write_image erase patch.bin PATCH_ADDRESS" \
  -c "reset run" \
  -c "shutdown"
```

> **VARIANTE A ist sicherer** — flasht die komplette Application.
> **VARIANTE B ist minimal** — ändert nur 2 Bytes, weniger Risiko.

### Schritt 5: Verifizieren

```bash
# Flash zurücklesen und mit Patched-Binary vergleichen
openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash read_image verify_after_flash.bin APP_START SIZE" \
  -c "shutdown"

python3 -c "
patched = open('tools/firmware/navee_meter_v2.0.3.1_PATCHED.bin', 'rb').read()
flashed = open('verify_after_flash.bin', 'rb').read()
if patched[16:] == flashed:  # Ohne Header vergleichen
    print('VERIFIZIERT — Patch ist im Flash!')
else:
    print('MISMATCH — Prüfen!')
"
```

### Schritt 6: Testen

1. SWD-Kabel abziehen
2. Scooter einschalten
3. Mit Android-App verbinden
4. CMD `0x6E` senden (Max Speed auf 30 km/h setzen)
5. Testfahrt

---

## Recovery

### Bei Problemen nach dem Flash

```bash
# Original-Firmware zurückspielen:
openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash write_image erase tools/firmware/backup_meter_FULL.bin 0x08000000" \
  -c "reset run" \
  -c "shutdown"
```

### Read-Protection (RDP)

Manche MCUs haben Read-Out Protection aktiviert. Falls OpenOCD meldet:
```
Error: flash read protected
```

Dann ist das Flash geschützt. Optionen:
- **Level 0:** Kein Schutz → normal lesen/schreiben
- **Level 1:** Lesen von außen gesperrt, aber über SWD unlockbar (löscht Flash!)
- **Level 2:** Permanent gesperrt → KEIN Zugang möglich

```bash
# RDP Level prüfen:
openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "stm32f1x options_read 0" \
  -c "shutdown"

# RDP Level 1 → Level 0 (ACHTUNG: Löscht den gesamten Flash!)
# Nur machen wenn die Original-Firmware als Datei vorliegt!
openocd -f tools/openocd_meter.cfg \
  -c "init" \
  -c "reset halt" \
  -c "stm32f1x unlock 0" \
  -c "reset halt" \
  -c "flash write_image erase tools/firmware/navee_meter_v2.0.3.1_PATCHED.bin APP_START" \
  -c "reset run" \
  -c "shutdown"
```

---

## Risiken

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|--------|-------------------|------------|------------|
| Falsches Pinout | Mittel | MCU-Beschädigung | Multimeter, Datenblatt |
| Flash-Löschung (RDP) | Niedrig | Bootloader weg | Backup VOR dem Unlock |
| Patch funktioniert nicht | Niedrig | Kein Speed-Limit-Change | Backup einspielen |
| Scooter bootet nicht | Niedrig | Nicht fahrbar | Full-Backup einspielen |

**Wichtigste Regel:** IMMER zuerst das Backup machen (Schritt 2) bevor irgendetwas geschrieben wird!

---

## Checkliste

- [ ] ST-Link V2 bestellt/vorhanden
- [ ] Dashboard geöffnet, SWD-Pads identifiziert
- [ ] MCU-Bezeichnung notiert
- [ ] OpenOCD installiert und Konfiguration angepasst
- [ ] SWD-Verbindung getestet
- [ ] **Full Flash Backup erstellt und SHA-256 gespeichert**
- [ ] Application-Adresse bestimmt
- [ ] Gepatchte Firmware geflasht
- [ ] Verify nach Flash
- [ ] Testfahrt mit CMD 0x6E
