# Direct Flash — Navee ST3 Pro (RTL8762C)

Anleitung zum direkten Flashen der Meter-Firmware über UART Download-Modus.

**MCU:** Realtek RTL8762C BLE SoC (Modul: RB8762-35A1)
**Flash:** Externer SPI Flash, Memory-Mapped ab 0x00800000
**Tool:** [rtltool](https://github.com/cyber-murmel/rtltool) (Python, Open Source)

**Warum direkt flashen?** Der OTA-Bootloader hat eine Integritätsprüfung die jede modifizierte Firmware ablehnt (verifiziert mit 10 verschiedenen Binaries inkl. XOR/SUM/CRC-Ausgleich, davon 2× Original erfolgreich). Die Prüfung ist kryptographisch oder proprietär und kann nicht über OTA umgangen werden.

---

## Architektur

```
┌─────────────────────────────────────────────────────┐
│              RTL8762C BLE SoC (RB8762-35A1)          │
│                                                     │
│  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ ARM       │  │ BLE      │  │ SPI Flash        │  │
│  │ Cortex-M4 │  │ Radio    │  │ (extern, 512KB+) │  │
│  │           │  │ 2.4 GHz  │  │                  │  │
│  └─────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│        │             │                 │             │
│        │   UART0 (0x40011000)          │             │
│        │   ← 19200 Baud (normal)       │             │
│        │   ← 115200 Baud (download)    │             │
│        │                               │             │
│  P0_3: LOW beim Boot → Download-Modus  │             │
└────────┼───────────────────────────────┼─────────────┘
         │                               │
    UART TX/RX                      SPI Flash
    (grüne Ader                     Memory Map:
     vom Stecker)                   0x800000 - Bootloader
                                    0x820000 - App FW ←── HIER PATCHEN
                                    0x80E000 - FTL Data
                                    0x80E400 - Config
```

---

## Hardware

### Benötigte Teile

| Teil | Preis | Zweck |
|------|-------|-------|
| USB-UART Adapter (3.3V!) | ~3€ | FTDI, CP2102 oder CH340 |
| Dupont-Kabel | ~2€ | Verbindung zum PCB |
| Dünner Draht / Jumper | ~1€ | P0_3 auf GND brücken |

> **WICHTIG:** Der RTL8762C arbeitet mit **3.3V Logik**! Keinen 5V UART-Adapter verwenden!

### Pinout am Dashboard-PCB

Beim Öffnen des Dashboards suche:

1. **UART-Pads:** Die grüne Ader vom internen Stecker ist TX (19200 Baud normal). Daneben sollte RX liegen.
2. **P0_3 Pad:** Muss beim Einschalten auf GND liegen um den Download-Modus zu aktivieren. Oft als Test-Pad beschriftet.
3. **GND:** Schwarze Ader oder Massefläche auf dem PCB.
4. **3.3V / VCC:** Für Stromversorgung (wird normal über den Scooter-Akku bereitgestellt).

### Verbindung

```
USB-UART Adapter          Dashboard PCB
─────────────────         ──────────────
TX  ──────────────────→   RX (UART Input)
RX  ←─────────────────   TX (grüne Ader)
GND ──────────────────→   GND (schwarze Ader)

Zusätzlich beim Boot:
GND ──── Jumper ──────→   P0_3 (Download-Mode Pin)
```

> Nach dem Booten im Download-Modus kann der Jumper von P0_3 entfernt werden.

---

## Software Setup

### rtltool installieren

```bash
# Repository klonen
git clone https://github.com/cyber-murmel/rtltool.git
cd rtltool

# Dependencies
pip3 install pyserial crccheck coloredlogs

# Realtek MP Tool herunterladen (enthält firmware0.bin für Handshake)
# Von: https://www.realmcu.com/en/Home/Product/93cc0582-3a3f-4ea8-82ea-76c6504e478a
# ZIP in rtl8762c/ Verzeichnis legen
# Kompatible Versionen: v1.0.5.8 oder v1.0.6.2
```

### Verbindung testen

```bash
# Scooter einschalten MIT P0_3 auf GND → Download-Modus
# USB-UART Adapter einstecken

# Port finden
ls /dev/tty.usbserial* /dev/tty.wchusbserial* /dev/cu.* 2>/dev/null

# Test: Chip-Info lesen
python3 rtltool.py -p /dev/tty.usbserial-XXX -vv read_mac
```

Erwartete Ausgabe:
```
## Performing Handshake
## Writing firmware0
Flash Size: XXX kiB
MAC: XX:XX:XX:XX:XX:XX
```

---

## Flash-Prozedur

### Schritt 1: Full Flash Backup (KRITISCH!)

```bash
# Gesamten Flash auslesen (512 KB typisch, kann bis 1 MB sein)
python3 rtltool.py -p /dev/PORT read_flash 0x800000 0x80000 backup_full_512k.bin

# SHA-256 für Backup-Verifizierung
shasum -a 256 backup_full_512k.bin > backup_full_512k.sha256
cat backup_full_512k.sha256
```

> **OHNE BACKUP NICHT WEITERMACHEN!** Das Backup enthält Bootloader, BLE-Stack,
> App-Firmware, Konfiguration und MAC-Adresse. Ohne Backup kein Recovery.

### Schritt 2: Firmware im Flash lokalisieren

```bash
python3 -c "
data = open('backup_full_512k.bin', 'rb').read()
orig = open('tools/firmware/navee_meter_v2.0.3.1_ORIGINAL.bin', 'rb').read()

# Suche die OTA-Firmware im Flash-Dump
idx = data.find(orig[:64])  # Suche nach den ersten 64 Bytes
if idx >= 0:
    flash_addr = 0x800000 + idx
    print(f'Firmware gefunden bei Flash-Offset 0x{idx:05X}')
    print(f'Flash-Adresse: 0x{flash_addr:08X}')
    print(f'Patch-Adresse: 0x{flash_addr + 0xF848:08X}')

    # Verifiziere den Patch-Punkt
    patch_off = idx + 0xF848
    print(f'Bytes an Patch-Stelle: 0x{data[patch_off]:02X} 0x{data[patch_off+1]:02X}')
    if data[patch_off] == 0x02 and data[patch_off+1] == 0xD9:
        print('→ Bestätigt: 02 D9 (bls) — bereit zum Patchen!')
    else:
        print('→ WARNUNG: Unerwartete Bytes! Patch-Offset prüfen!')
else:
    print('Firmware NICHT im Flash gefunden!')
    print('Header-Suche...')
    idx2 = data.find(b'T2202')
    if idx2 >= 0:
        print(f'  T2202 Header bei Flash-Offset 0x{idx2:05X} (0x{0x800000+idx2:08X})')
"
```

### Schritt 3: Nur den Patch schreiben (minimal-invasiv)

```bash
# Erstelle eine 4-Byte Patch-Datei (2 Bytes Patch + 2 Bytes Kontext für Alignment)
python3 -c "
# Patch: 02 D9 → 00 BF (NOP statt bls)
# Die Patch-Stelle muss 4KB-aligned geschrieben werden (Flash-Sektor)
# Daher: ganzen 4KB-Sektor lesen, patchen, zurückschreiben

import struct
PATCH_FILE_OFFSET = 0xF848
SECTOR_SIZE = 0x1000  # 4 KB

# Sektor-Nummer und Offset innerhalb des Sektors
sector_num = PATCH_FILE_OFFSET // SECTOR_SIZE  # = 15 (0xF)
offset_in_sector = PATCH_FILE_OFFSET % SECTOR_SIZE  # = 0x848

print(f'Patch bei File-Offset 0x{PATCH_FILE_OFFSET:04X}')
print(f'Sektor {sector_num} (0x{sector_num:X}), Offset im Sektor: 0x{offset_in_sector:03X}')
print(f'Flash-Sektor-Adresse: FW_BASE + 0x{sector_num * SECTOR_SIZE:05X}')
print()
print('Nutze den vollen Sector-Read/Modify/Write Ansatz:')
print('1. Sektor lesen: rtltool read_flash ADDR 0x1000 sector.bin')
print('2. Patch: Bytes 0x848-0x849 ändern (02 D9 → 00 BF)')
print('3. Sektor schreiben: rtltool write_flash ADDR sector.bin')
"
```

Dann ausführen:

```bash
# FW_BASE = Flash-Adresse aus Schritt 2 (z.B. 0x820000)
# SECTOR_ADDR = FW_BASE + 0xF000 (Sektor 15)

# 1. Sektor lesen
python3 rtltool.py -p /dev/PORT read_flash SECTOR_ADDR 0x1000 sector_backup.bin

# 2. Patch anwenden
python3 -c "
data = bytearray(open('sector_backup.bin','rb').read())
print(f'Vor Patch: 0x{data[0x848]:02X} 0x{data[0x849]:02X}')
assert data[0x848] == 0x02 and data[0x849] == 0xD9, 'FALSCHE BYTES! Abbruch!'
data[0x848] = 0x00  # NOP high byte
data[0x849] = 0xBF  # NOP low byte
print(f'Nach Patch: 0x{data[0x848]:02X} 0x{data[0x849]:02X}')
open('sector_patched.bin','wb').write(data)
print('sector_patched.bin erstellt')
"

# 3. Gepatchten Sektor zurückschreiben
python3 rtltool.py -p /dev/PORT write_flash SECTOR_ADDR sector_patched.bin

# 4. Verifizieren
python3 rtltool.py -p /dev/PORT verify_flash SECTOR_ADDR sector_patched.bin
```

### Schritt 4: Neustart und Test

1. P0_3 Jumper entfernen (falls noch verbunden)
2. Scooter aus/ein (normaler Boot, nicht Download-Modus)
3. Mit Android-App verbinden
4. CMD `0x6E` senden: Max Speed auf 30 km/h
5. Testfahrt!

---

## Recovery

### Original-Firmware wiederherstellen

```bash
# Option A: Nur den gepatchten Sektor zurücksetzen
python3 rtltool.py -p /dev/PORT write_flash SECTOR_ADDR sector_backup.bin

# Option B: Gesamtes Flash-Backup wiederherstellen
python3 rtltool.py -p /dev/PORT write_flash 0x800000 backup_full_512k.bin
```

### OTA-Rollback

Nach dem direkten Patch funktioniert OTA weiterhin — der Bootloader ist unverändert. Die offizielle Navee-App kann jederzeit ein reguläres Firmware-Update installieren das den Patch überschreibt.

---

## Risiken

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|--------|-------------------|------------|------------|
| Falscher Sektor gepatcht | Niedrig | Firmware defekt | Sektor-Backup VOR Patch |
| Flash-Backup unvollständig | Niedrig | Kein Recovery | SHA-256 Verify |
| P0_3 falsch identifiziert | Mittel | Download-Modus startet nicht | Datenblatt/Traces prüfen |
| 5V statt 3.3V UART | Mittel | Chip-Beschädigung | **NUR 3.3V Adapter!** |
| Scooter bootet nicht | Niedrig | Nicht fahrbar | Full Backup einspielen |

---

## Checkliste

- [ ] USB-UART Adapter (3.3V!) vorhanden
- [ ] Dashboard geöffnet, UART-Pads identifiziert
- [ ] P0_3 Pin identifiziert
- [ ] rtltool installiert + MP Tool ZIP heruntergeladen
- [ ] Download-Modus funktioniert (read_mac erfolgreich)
- [ ] **Full Flash Backup erstellt + SHA-256 gespeichert**
- [ ] Firmware im Flash lokalisiert (T2202 Header gefunden)
- [ ] Patch-Stelle verifiziert (02 D9 an erwartetem Offset)
- [ ] Sektor-Backup erstellt
- [ ] Patch geschrieben + verifiziert
- [ ] Normaler Boot erfolgreich
- [ ] CMD 0x6E → Speed-Limit geändert
- [ ] Testfahrt

---

## Referenzen

- [rtltool](https://github.com/cyber-murmel/rtltool) — RTL8762C Flash-Tool
- [RTL8762C Datenblatt](https://www.realmcu.com/en/Home/Product/93cc0582-3a3f-4ea8-82ea-76c6504e478a) — Realtek
- [Realtek BeeBee2 SDK](https://github.com/nicka101/RTL8762C-SDK-GCC) — Inoffizielle SDK-Portierung
