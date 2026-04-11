# Hardware — Navee ST3 Pro

[English](HARDWARE.md) | [Deutsch](HARDWARE_DE.md)

Vollständige Hardware-Referenz für das Dashboard-Gerät des Navee ST3 Pro E-Scooters, interne Verkabelung, Motorcontroller-Schnittstelle und Debug-Zugang.

---

## Inhaltsverzeichnis

- [Übersicht](#übersicht)
- [Dashboard (Meter Unit)](#dashboard-meter-unit)
- [Interne Verkabelung — Dashboard-zu-Controller-Kabel](#interne-verkabelung--dashboard-zu-controller-kabel)
- [Motorcontroller](#motorcontroller)
- [Akku](#akku)
- [Geschwindigkeitsbegrenzer-Kabel — Ältere Revisionen](#geschwindigkeitsbegrenzer-kabel--ältere-revisionen)
- [RTL8762C Download-Modus](#rtl8762c-download-modus)
- [Flash-Speicher-Layout](#flash-speicher-layout)
- [BLE Radio](#ble-radio)
- [Fotos](#fotos)

---

## Übersicht

| Eigenschaft | Wert |
|-------------|------|
| Modell | Navee ST3 Pro |
| PID (DE-Markt) | 23452 — 22 km/h Firmware-Limit |
| PID (Global) | 23451 — 30 km/h Firmware-Limit |
| Markt | Deutschland / EU-reguliert |
| Dashboard MCU | Realtek RTL8762C BLE SoC |
| UART-Baudrate | 19200 (Normalbetrieb) |

Der ST3 Pro verwendet ein Single-Chip-Design im Dashboard: Der Realtek RTL8762C übernimmt sowohl die BLE-Kommunikation mit der Companion-App als auch die gesamte Dashboard-Logik (Geschwindigkeitsanzeige, Modusauswahl, Lichtsteuerung). Es gibt kein separates BLE-Modul — Radio und Anwendungs-Firmware laufen auf demselben MCU.

---

## Dashboard (Meter Unit)

Das Dashboard ist die primäre Bedienoberfläche und die Einheit, die drahtlos mit der Android/iOS-App kommuniziert.

| Eigenschaft | Wert |
|-------------|------|
| MCU | Realtek RTL8762C BLE SoC |
| CPU-Kern | ARM Cortex-M4F, 40 MHz |
| Modul | RB8762-35A1 (Navee Custom-Modul) |
| Seriennummer | 251210A5629ABB3E |
| MAC-Adresse | 10:A5:62:9A:BB:3E (lesbar via `rtltool read_mac`) |
| FCC ID | 2A4GZ-RB87623SAI |
| IC | 28570-RB876235AI |
| Flash | Externer SPI Flash, mindestens 512 KB, Memory-Mapped ab `0x00800000` |
| BLE Radio | Integriertes 2,4 GHz |
| Firmware-Speicher | SPI Flash |
| Firmware-Update | OTA via BLE (XMODEM-Protokoll über Write Characteristic) |

Der RTL8762C ist ein Single-Chip-Design. BLE-Kommunikation und die gesamte Dashboard-Anwendungslogik (Durchsetzung des Geschwindigkeitslimits, Moduswechsel, Lichtsensorsteuerung) laufen gemeinsam auf diesem einen MCU. Die Firmware ist auf externem SPI Flash gespeichert und über die BLE-Schnittstelle OTA-aktualisierbar — der Bootloader erzwingt jedoch eine Integritätsprüfung, die jedes modifizierte Binary ablehnt.

---

## Interne Verkabelung — Dashboard-zu-Controller-Kabel

Ein 5-adriges Kabel verbindet das Dashboard-Gerät mit dem Motorcontroller im Deck.

| Aderfarbe | Funktion | Gemessene Spannung | Hinweise |
|-----------|----------|-------------------|----------|
| Schwarz | GND | 0 V | Gemeinsame Masse |
| Rot | VCC Akku | 53,04 V | **GEFAHR — Akkuspannung, NICHT an MCU anschließen** |
| Blau | VCC Dashboard | 52,2 V | **GEFAHR — Akkuspannung, NICHT an MCU anschließen** |
| Gelb | **Controller RX** | 3,8 V (Idle) | Dashboard → Controller Dateneingang. Protokoll: `0x51`/`0xAE` Frames, 14 Bytes |
| Grün | **Controller TX** | 4,12 V (Idle) | Controller → Dashboard Datenausgang. Echo `0x61`/`0x9E` + Antworten `0x64`/`0x9B` |

**Warnung:** Die roten und blauen Adern führen volle Akkuspannung (50 V+). Das Anschließen einer dieser Leitungen an einen Mikrocontroller, USB-UART-Adapter oder ein 3,3-V-/5-V-Logikgerät zerstört das Gerät sofort. Vor jeder Verbindung immer mit einem Multimeter messen. Nur die gelbe, grüne und schwarze Ader sind sicher für die Verbindung mit externer Hardware (bei geeigneten Spannungspegeln).

### Zweidraht-Vollduplex-UART

Der UART ist Standard-Zweidraht-Vollduplex, NICHT Eindraht-Halbduplex:

| Ader | Richtung | Protokoll | Frame-Format |
|------|----------|-----------|-------------|
| **Gelb** | Dashboard → Controller | `0x51`/`0xAE` (14 Bytes) | `51 10 09 [MODE] [LIGHT] [88] [?] [?] [SPD1] [?] [SPEED] [?] [CHK] AE` |
| **Grün** | Controller → Dashboard | `0x61`/`0x9E` + `0x64`/`0x9B` | Gleiches Format wie BLE-interne UART-Frames |

Das Dashboard sendet Befehlsframes auf der **gelben** Ader. Der Controller antwortet auf der **grünen** Ader. Die 0x61-Frames auf Grün sind Controller-internes Echo (der Controller spiegelt empfangene Befehle auf seiner TX-Leitung), kein Shared Bus.

**Spannungspegel:** Gelb arbeitet bei 3,8V, Grün bei 4,12V. Standard-3,3V-USB-UART-Adapter (CP2102) sind zu niedrig für Gelb. Ein Arduino Nano (5V) mit dem TX-Pin funktioniert, da der Controller 5V-Eingang toleriert. Das Trennen von Gelb vom Dashboard verursacht Fehlerpiepen (Fehler: kein Dashboard-Signal).

**Speed-Limit-Byte:** Yellow-Wire-Frame Offset 10 enthält den Speed-Limit-Wert (`0x16` = 22 km/h für DE). Der Controller ignoriert diesen Wert jedoch — das Speed-Limit wird intern durch den BLDC-Firmware-Ländercode (`0xCF` = DE) durchgesetzt.

Vollständiges Frame-Format: [INTERNAL_UART_PROTOCOL.md](INTERNAL_UART_PROTOCOL.md) inkl. Yellow-Wire-Protokoll.

---

## Motorcontroller

| Eigenschaft | Wert |
|-------------|------|
| MCU | **LKS32MC081C8T8** (Linkosemi) |
| CPU-Kern | ARM Cortex-M0 |
| Flash | 64 KB |
| RAM | 8 KB |
| SWD | Ungeschützt — aber physisch nicht zugänglich (vergossen) |
| Standort | Im Deck, vergossen in Kunstharz |
| Zugänglichkeit | Nicht ohne destruktive Demontage zugänglich |
| Kommunikation | UART bei 19200 Baud — empfängt auf **Gelb**, sendet auf **Grün** |
| Geschwindigkeitslimit | Hardcoded in Firmware via Region-Byte (`0xCF` = DE, `0xB7` = Global) |
| Firmware (DE) | v0.0.1.5, 53.376 Bytes, Modell T2324 |
| Firmware (Global) | v0.0.1.1, 47.232 Bytes, Modell T2324 |

Der Motorcontroller ist vollständig in Vergussharz eingebettet. Der physische Zugang zu seinem Inneren erfordert eine destruktive Demontage, die nicht rückgängig gemacht werden kann.

### Speed-Limit — Endgültig bestätigt

Das Speed-Limit wird vollständig innerhalb der eigenen Firmware des Controllers durchgesetzt. Dies wurde durch 12 Angriffsvektoren über 4 Wochen bestätigt:

1. **BLE CMD 0x6E** — ACK erhalten, von Firmware ignoriert
2. **UART MitM auf Grün** (v1) — Controller ignorierte manipulierte Frames (1168 Frames, falsche Leitung)
3. **UART MitM auf Gelb** (v2) — Richtige Leitung, 795 Frames modifiziert, Controller bleibt bei 22 km/h
4. **Dashboard-Ersatz** — Arduino generiert eigene 0x51-Frames mit Speed=40, Controller echot interne Speed-Werte (22/21)
5. **Bootloader-Probes** — STM32-Sync, Text-Befehle, LKS32-Patterns, Yellow-DFU-Frames — alle gescheitert bei 19200 und 115200 Baud
6. **BLE OTA (dfu_start 2)** — Dashboard blockiert BLDC-Firmware-Relay

Die Controller-Firmware verwendet ein dreistufiges Speed-Limit-System: Region-Byte (0xCF=DE), PWM-Skalierungstabelle und Geschwindigkeitsprogressionstabelle. Die UART-Speed-Bytes sind nur Telemetrie — der Controller nutzt sie nicht als Befehle.

Vollständige Berichte: [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) und [BLDC_DFU_ANALYSIS.md](BLDC_DFU_ANALYSIS.md).

---

## Akku

| Eigenschaft | Wert |
|-------------|------|
| Chemie | Lithium-Ionen |
| Zellenfarbe | Blau (im Deck sichtbar) |
| Nennspannung | ~53 V |
| Stecker | Intern, mit manuellem Trenner via Wago-Klemmen |

Das Akkupack ist im Deck zugänglich. Eine manuelle Trennung über Wago-Klemmenverbinder ist ohne Spezialwerkzeug möglich, was bei Hardware-Modifikationen sichere Arbeitsbedingungen ermöglicht. Vor dem Herstellen elektrischer Verbindungen zum Dashboard oder Kabelbaum stets den Akku trennen.

---

## Geschwindigkeitsbegrenzer-Kabel — Ältere Revisionen

Frühe Hardware-Revisionen des ST3 Pro enthielten eine dedizierte weiße Ader, die als physischer Geschwindigkeitsbegrenzer diente. Das Durchtrennen dieser Ader entfernte die Geschwindigkeitsbegrenzung bei diesen Geräten.

**Aktuelle Revisionen (2024 und später) haben diese Ader nicht mehr.** Das Geschwindigkeitslimit bei aktueller Hardware wird vollständig per Firmware durchgesetzt — es gibt keine physische Ader, die durchgetrennt werden kann. Versuche, das Limit zu umgehen, müssen direkt auf die Firmware abzielen.

Quelle: rollerplausch.com Community-Forum, mehrere bestätigte Nutzerberichte.

---

## RTL8762C Download-Modus

Der RTL8762C unterstützt einen UART-basierten Download-Modus, der das vollständige Lesen und Schreiben des SPI Flash ermöglicht und den OTA-Bootloader komplett umgeht. Dies ist die einzige bestätigte Methode, um ein gepatchtes Firmware-Binary auf die aktuelle Hardware-Revision aufzuspielen.

| Eigenschaft | Wert |
|-------------|------|
| Aktivierung | Pin P0_3 beim Boot auf LOW halten |
| Download-Baudrate | 115200 |
| Normalbetrieb-Baudrate | 19200 |
| Tool | [rtltool](https://github.com/wuwbobo2021/rtltool) |
| Logikpegel | **3,3 V — KEINEN 5-V-UART-Adapter verwenden** |
| Benötigte Hardware | USB-UART-Adapter (3,3 V), Zugang zum P0_3-Pad auf der Platine, GND |

### Verifiziertes Download-Modus-Verfahren

Das folgende Setup wurde beim erfolgreichen 512-KB-Flash-Dump bestätigt:

- **Stromversorgung:** Arduino-Board liefert geregelte 3,3 V an die Dashboard-Platine (Scooter-Akku vollständig getrennt). Nicht mit verbundenem Akku versuchen.
- **USB-UART-Adapter:** CP2102-basierter Adapter bei 3,3-V-Logikpegel. Keinen 5-V-Adapter verwenden.
- **P0_3-Aktivierung:** Jumper-Draht von P0_3-Pad nach GND, vor und während des Einschaltens gehalten.

**Schritt für Schritt:**

1. Den Scooter-Akku vollständig trennen.
2. Das Dashboard-Gehäuse öffnen und die UART TX/RX-Pads, GND und das P0_3-Testpad auf der Platine lokalisieren.
3. Den CP2102-Adapter verbinden: TX an RX-Pad, RX an TX-Pad, GND an GND.
4. Die Arduino 3,3-V- und GND-Pins mit den Dashboard 3,3-V- und GND-Pads verbinden.
5. P0_3 mit einem Jumper-Draht mit GND brücken.
6. Strom anlegen (Arduino USB verbinden). Der RTL8762C bootet in den Download-Modus.
7. `rtltool`-Befehle ausführen (Flash lesen, Flash schreiben, MAC lesen usw.).
8. Nach der Sitzung den P0_3-Jumper entfernen und neu starten, um zur normalen Firmware zurückzukehren.

Vollständiges Schritt-für-Schritt-Flash-Verfahren inklusive Backup, Patch-Anwendung und Verifikation: [SWD_FLASH_GUIDE.md](SWD_FLASH_GUIDE.md).

---

## Flash-Speicher-Layout

Der RTL8762C verwendet einen externen SPI-Flash-Chip, Memory-Mapped ab `0x00800000`. Das folgende Layout ist das verifizierte Layout aus dem tatsächlichen 512-KB-Flash-Dump, der via rtltool gewonnen wurde.

### Dual-Bank-Architektur

Der Flash verwendet ein Dual-Bank-(A/B-)Layout für sichere OTA-Updates. Bank A enthält die aktuell laufende Anwendungs-Firmware. Bank B (OTA-Staging-Bereich) enthält die eingehende Firmware während einer OTA-Übertragung. Nach erfolgreicher Integritätsprüfung wechselt der Bootloader zu Bank B, und Bank A wird der nächste Staging-Bereich. Bootloader und BLE-Stack-Patches belegen den unteren Adressbereich und werden von OTA-Updates nicht berührt.

### Verifiziertes Layout

| Adressbereich | Größe | Inhalt |
|--------------|-------|--------|
| `0x00800000` | — | Reserviert (0xFF) |
| `0x00801000` – `0x00802FFF` | 8 KB | Systemkonfiguration, Boot-Parameter |
| `0x00803000` – `0x00803FFF` | 4 KB | Patch-Image-Header (BLE Stack) |
| `0x00804000` – `0x0080DFFF` | 40 KB | Patch-Code (BLE Stack, aktiv) |
| `0x0080E000` – `0x0082FFFF` | 136 KB | App-Firmware — Bank A (aktiv). Patch-Ziel bei `0x0081D448` |
| `0x00840000` – `0x00841FFF` | 8 KB | OTA-Header-Bereich |
| `0x00844000` – `0x00865FFF` | 136 KB | OTA-Staging — Bank B |
| `0x00876000` | — | Zusätzliche Konfiguration |

Die Patch-Stelle des Geschwindigkeitslimits liegt bei der absoluten Flash-Adresse `0x0081D448` (Bank A). Dies wurde bestätigt, indem der `T2202`-Firmware-Header im Dump gefunden und der Offset der `02 D9`-Branch-Instruktion aus der Ghidra-Analyse berechnet wurde. Genaue Details zum 1-Byte-Patch: [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md#der-patch-1-byte).

Der Bootloader verifiziert Bank B mit SHA-256 vor dem Wechsel. Direktes Schreiben via Download-Modus (rtltool) zielt auf Bank A und umgeht diese Prüfung vollständig.

---

## BLE Radio

Die BLE-Schnittstelle ist der primäre Kommunikationskanal zwischen der Companion-App und dem Scooter. Alle Fahrtsteuerungen, Telemetriedaten und Firmware-Updates laufen über diese Characteristics.

| Eigenschaft | Wert |
|-------------|------|
| Service UUID | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Write Characteristic | `0000b002-0000-1000-8000-00805f9b34fb` |
| Notify Characteristic | `0000b003-0000-1000-8000-00805f9b34fb` |
| Advertised Names | `NAVEE`, `NV`, `ST3` |
| Authentifizierung | AES-128-ECB mit 5 rotierenden Schlüsseln |
| Scan-Advertisement | Service UUID nicht immer im Scan-Record enthalten; direkte Verbindung per MAC-Adresse ist zuverlässiger |

Der Scooter enthält den Service UUID nicht immer in seinem BLE-Advertisement. Die Verbindung über eine gespeicherte MAC-Adresse (Direct Connect) ist beim Wiederverbinden mit einem bekannten Gerät zuverlässiger als die Service-UUID-Erkennung.

Die PID ist im BLE-Scan-Record bei Bytes 6–7 kodiert (Little-Endian 16-Bit-Integer). PID 23452 identifiziert das Gerät für den deutschen Markt mit dem 22-km/h-Firmware-Limit.

Vollständiges BLE-Protokoll inklusive Frame-Format, aller Befehls-Bytes, Telemetrie-Parsing und der DFU-Update-Sequenz: [PROTOCOL.md](PROTOCOL.md).

Details zu Authentifizierungsschlüsseln und dem Auth-Ablauf: [AUTHENTICATION.md](AUTHENTICATION.md).

---

## Fotos

Fotos des geöffneten Dashboard-Gehäuses, PCB-Layout, Modul-Beschriftungen und Pad-Positionen werden hier ergänzt.

Geplante Ergänzungen:
- Dashboard-Platine Draufsicht (Modul, SPI-Flash-Chip, UART-Pads, P0_3-Testpad)
- Dashboard-Stecker und Kabelbaum mit Farbbeschriftungen
- Deck-Innenraum mit Akkuzellen und Motorcontroller-Verguss

---

## Siehe auch

- [PROTOCOL.md](PROTOCOL.md) — Vollständige BLE-Protokoll-Referenz
- [AUTHENTICATION.md](AUTHENTICATION.md) — Auth-Ablauf und AES-Schlüssel
- [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) — Methodik und Erkenntnisse, inkl. Geschwindigkeitslimit-Analyse
- [SWD_FLASH_GUIDE.md](SWD_FLASH_GUIDE.md) — Schritt-für-Schritt-Direktflash-Anleitung via RTL8762C Download-Modus
- [INTERNAL_UART_PROTOCOL.md](../archive/INTERNAL_UART_PROTOCOL.md) — Internes UART-Frame-Format (Dashboard zu Controller)
