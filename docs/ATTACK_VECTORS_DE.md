[English](ATTACK_VECTORS.md) | [Deutsch](ATTACK_VECTORS_DE.md)

# Angriffsvektoren — Navee ST3 Pro Geschwindigkeitslimit

Ehrliche Bewertung aller unternommenen Ansätze zur Modifikation des 22-km/h-Geschwindigkeitslimits (PID 23452, deutscher Markt).

## Übersichtstabelle

| # | Vektor | Status | Aufwand | Risiko |
|---|--------|--------|---------|--------|
| 1 | BLE CMD 0x6E (Max Speed) | Gescheitert | Niedrig | Keins |
| 2 | UART MitM (Arduino) | Gescheitert | Mittel | Niedrig |
| 3 | Firmware-Patch (Ghidra) | Patch gefunden | Hoch | k. A. |
| 4 | OTA Flash (BLE XMODEM) | SHA-256 geknackt | Sehr hoch | Niedrig |
| 5 | SPI Flash Direkt (rtltool) | Verifiziert | Mittel | Mittel |
| 6 | Controller-Tausch (AliExpress) | Bewährt | Niedrig | Niedrig |
| 7 | Geschwindigkeitsbegrenzer-Kabel | N/A (neue Revision) | Niedrig | Niedrig |
| 8 | OTA mit SHA-256-Fix | Bereit (ungetestet) | Mittel | Niedrig |

## Detaillierte Analyse

### 1. BLE-Befehl 0x6E — Max-Speed-Einstellung
**Status: Gescheitert**

Die offizielle Navee-App sendet CMD 0x6E mit Payload [0x01, speed_kmh] um die Höchstgeschwindigkeit zu setzen. Der Scooter bestätigt den Befehl (ACK), ignoriert ihn jedoch vollständig. Das `lift_speed_limit`-Flag in der Firmware (bei sys_stc[0x4A]) muss auf `0x02` stehen, damit CMD 0x6E wirksam wird. Ohne den Firmware-Patch wird dieses Flag für PID 23452 nie gesetzt.

**Warum es scheitert:** Die Geschwindigkeitslimit-Funktion (FUN_0800ad02) prüft den Ländercode (abgeleitet von der PID). Für Deutschland (Ländercode 3) gibt sie unabhängig vom CMD-0x6E-Wert 22,5 km/h zurück. Nur wenn `lift_speed_limit == 0x02` gilt, verwendet sie die benutzerdefinierte Geschwindigkeit aus sys_stc[0x47].

### 2. UART MitM — Arduino-Abfanglösung
**Status: Gescheitert**

Ein Arduino UNO wurde als Man-in-the-Middle auf die grüne UART-Ader zwischen Dashboard und Motorcontroller gesetzt. Der Arduino parste Frame A (Dashboard-Status, 15 Bytes) und änderte die Bytes 6–7 (Geschwindigkeitswerte) von 0x17/0x15 auf 0x1E/0x1E (30 km/h), wobei die Prüfsumme neu berechnet wurde.

Über 1168 Frames wurden erfolgreich mit korrekten Prüfsummen modifiziert. Der Motorcontroller empfing und verarbeitete diese Frames. **Aber der Scooter fuhr weiterhin exakt 22 km/h.**

**Warum es scheitert:** Die Geschwindigkeits-Bytes in Frame A (Bytes 6–7) sind KEINE Geschwindigkeitslimits — es handelt sich um Telemetrie-/Anzeigewerte, die das Dashboard an den Controller sendet. Das tatsächliche Geschwindigkeitslimit wird innerhalb der Dashboard-Firmware berechnet und durch einen anderen Mechanismus durchgesetzt (wahrscheinlich Motor-PWM-/Strombegrenzungsparameter, nicht diese spezifischen Bytes).

**Kernaussage:** Der Controller akzeptiert extern manipulierte Frames für Geschwindigkeitslimitänderungen NICHT. Das Geschwindigkeitslimit muss aus der Dashboard-Firmware selbst stammen, gesendet als authentisches Berechnungsergebnis.

### 3. Firmware-Patch — Ghidra-Analyse
**Status: Patch identifiziert (noch nicht installiert)**

Mittels Ghidra-Headless-Analyse der heruntergeladenen Meter-Firmware (v2.0.3.1, 138240 Bytes) wurde die Geschwindigkeitslimit-Funktion identifiziert:

```
FUN_0800ad02 (File offset: 0xAD02):
  if (sys_stc[0x4A] == 0x02) {        // lift_speed_limit Flag
      return sys_stc[0x47] * 10 + 5;  // Benutzerdefinierte Geschwindigkeit via BLE CMD 0x6E
  } else {
      return PID_DEFAULT_TABLE[area_code];  // 22,5 km/h für Deutschland
  }
```

**Der Patch (1 Byte):**
- File Offset 0xF848: `02 D9` (BLS — Branch if less/same) → `00 BF` (NOP)
- Dadurch wird der bedingte Branch entfernt, sodass der Code immer in den Custom-Speed-Pfad fällt
- Nach dem Patchen kann CMD 0x6E einen beliebigen Geschwindigkeitswert setzen

### 4. OTA Flash — BLE XMODEM-Transfer
**Status: SHA-256-Prüfsumme geknackt (2026-03-20)**

Der OTA-Flasher wurde vollständig entwickelt und verifiziert:
- Vollständiges DFU-Protokoll: `dfu_start` → `ble_rand` → `ble_key` → XMODEM → EOT
- APK-exakte State Machine (asyncio.Event, ACK-Block-Validierung)
- 1080/1080 Blöcke erfolgreich übertragen (135 KB, 34–68 Sekunden)
- Original-Firmware: `rsq dfu_ok` empfangen, Firmware installiert (2/2 Versuche)
- **JEDE modifizierte Firmware: abgelehnt (0/10 Versuche)** — vor dem SHA-256-Fix

Sogar das Ändern eines einzelnen Bytes im 0xFF-Padding-Bereich führte zur Ablehnung. Der Bootloader verwendet SHA-256 zur Integritätsprüfung.

**SHA-256 am 2026-03-20 geknackt.** Algorithmus und genaue Platzierung im Firmware-Image wurden durch Analyse des Realtek Bee2 SDK-Quellcodes gefunden (`silent_dfu_flash.c`). Ein gepatchtes OTA-Firmware-Binary mit korrekt neu berechnetem SHA-256 wurde erstellt: `navee_meter_v2.0.3.1_PATCHED_OTA.bin`. OTA-Patching ist nun theoretisch möglich, wurde jedoch noch nicht an einem funktionierenden Dashboard getestet — die Testplatine wurde durch einen Kurzschluss beschädigt, bevor der End-to-End-OTA-Test abgeschlossen werden konnte.

**Vor der Lösung getestete Prüfsummen (alle ohne Treffer):**
CRC-16/XMODEM, CRC-16/CCITT, CRC-16/ARC, CRC-16/MODBUS, CRC-32 (Standard), CRC-32 (STM32), XOR-32 (Wort), XOR-8 (Byte), SUM-8, SUM-16, SUM-32, Fletcher-16, Fletcher-32, Adler-32, MD5, SHA-1, SHA-256, HMAC-MD5 (mit allen 5 AES-Schlüsseln), Brute-Force CRC-32 an jeder 4-Byte-Position, Brute-Force CRC-16 an jeder 2-Byte-Position.

### 5. SPI Flash Direkt — rtltool via UART
**Status: Verifiziert**

Der Dashboard-MCU ist ein Realtek RTL8762C, der via UART programmiert werden kann, wenn Pin P0_3 beim Boot auf LOW gehalten wird. Mit [rtltool](https://github.com/wuwbobo2021/rtltool) kann der gesamte SPI Flash gelesen und geschrieben werden, wobei die Integritätsprüfung des OTA-Bootloaders vollständig umgangen wird.

**Verifizierte Ergebnisse:**
- Vollständiger 512-KB-Flash-Dump erfolgreich via rtltool abgeschlossen
- Patch-Byte an Flash-Adresse `0x0081D448` geschrieben (die `02 D9` → `00 BF`-Substitution)
- Patch verifiziert durch erneutes Lesen des Flash-Sektors nach dem Schreiben

**Verwendetes Verfahren:**
1. Dashboard geöffnet, Stromversorgung via Arduino 3,3-V-Netzteil (Scooter-Akku isoliert)
2. CP2102 USB-UART-Adapter verbunden (3,3-V-Logik)
3. P0_3 mit Jumper-Draht auf GND gebrückt, Strom angelegt → RTL8762C wechselte in den Download-Modus
4. Gesamten 512-KB-Flash gedumpt (Backup)
5. Firmware anhand des `T2202`-Headers lokalisiert; Patch-Ziel bei `0x0081D448` bestätigt
6. Gepatchten Sektor via rtltool zurückgeschrieben
7. Durch erneutes Lesen der gepatchten Adresse verifiziert

**Hinweis:** Die Testplatine war vor diesen Arbeiten durch einen Kurzschluss beschädigt worden (Scooter war AN während der Platinenentnahme). Flash-Operationen gelangen auf der beschädigten Platine; die Funktionsverifikation der gepatchten Firmware wartet auf ein funktionierendes Ersatz-Dashboard.

### 6. Controller-Tausch — Global-Version
**Status: Bewährt (durch Community)**

Das Ersetzen des Motorcontrollers durch eine „Global"-Version (ohne DE-Geschwindigkeitslimit) hebt die 22-km/h-Beschränkung auf. Controller sind auf AliExpress für ~30–50 EUR erhältlich.

**Vorteile:** Nachweislich funktionierend, kein Firmware-Wissen erforderlich
**Nachteile:** Kosten, Garantieverlust, möglicherweise anderes Controller-Verhalten

Quelle: rollerplausch.com Community

### 7. Geschwindigkeitsbegrenzer-Kabel — Hardware-Trennung
**Status: Nicht anwendbar (neue Revision)**

Ältere Hardware-Revisionen hatten eine dedizierte weiße Ader, die beim Durchtrennen das Geschwindigkeitslimit aufhob. Aktuelle Revisionen (2024+) haben diese Ader nicht mehr. Das Geschwindigkeitslimit ist nun vollständig per Firmware durchgesetzt.

Quelle: rollerplausch.com Community

### 8. OTA mit SHA-256-Fix
**Status: Bereit (ungetestet)**

Nach dem in Vektor 4 dokumentierten SHA-256-Crack wurde ein Python-Skript (`patch_firmware.py`) geschrieben, das den vollständigen Patch-Workflow automatisiert:

1. Nimmt ein beliebiges Navee-Meter-Firmware-Binary als Eingabe
2. Wendet den Geschwindigkeitslimit-Patch an (`02 D9` → `00 BF` am korrekten Offset)
3. Berechnet die SHA-256-Prüfsumme neu unter Verwendung des Algorithmus aus dem Realtek Bee2 SDK (`silent_dfu_flash.c`)
4. Schreibt die korrigierte Prüfsumme an die erwartete Header-Position im Binary zurück
5. Gibt ein zum Flashen fertiges OTA-Binary aus

Die Ausgabedatei `navee_meter_v2.0.3.1_PATCHED_OTA.bin` ist das Ergebnis der Ausführung von `patch_firmware.py` gegen die offizielle Firmware v2.0.3.1. End-to-End-OTA-Tests (Transfer → Bootloader-Akzeptanz → Boot) wurden noch nicht durchgeführt, da die Testplatine vor diesem Schritt beschädigt wurde.

## Empfehlungen

**Für neue Nutzer:** OTA mit SHA-256-Fix (Vektor 8) ist nun der empfohlene Ansatz. Er erfordert keinen Hardware-Zugang — nur eine BLE-Verbindung und das `patch_firmware.py`-Skript. Der SHA-256-Algorithmus ist gelöst, und das gepatchte Binary ist bereit. End-to-End-OTA-Tests sind der einzig verbleibende Schritt, bevor dieser Weg vollständig bestätigt ist.

**Für die meisten Nutzer (heute bewährt):** Controller-Tausch (Vektor 6) ist weiterhin die einfachste bestätigte funktionierende Lösung.

**Für Reverse Engineers:** SPI-Flash-Direktprogrammierung (Vektor 5) ist vollständig verifiziert. Der Flash wurde erfolgreich gedumpt und gepatcht. Das Öffnen des Dashboards und der Zugang zu den UART/P0_3-Pads ist erforderlich, umgeht jedoch die Bootloader-Integritätsprüfung vollständig. Die Funktionsverifikation auf einer funktionierenden Platine steht noch aus.

**Nicht empfohlen:** Manuelles OTA-Prüfsummen-Suchen ohne Verwendung von `patch_firmware.py`. Der SHA-256-Algorithmus ist nun bekannt — weitere Brute-Force-Versuche sind überflüssig.
