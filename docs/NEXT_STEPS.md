# Next Steps — Stand 2026-04-17

**Dies ist der aktuelle letzte Stand. Alle nachfolgend nicht aufgeführten Pfade sind empirisch oder durch Datasheet-Fakten ausgeschlossen.** Dieses Dokument ist die konkrete Ausgangsbasis für die nächste Arbeits-Session.

## Warum dieses Dokument existiert

Nach ~4 Wochen intensiver Forschung (App-Decompile, Ghidra auf Dashboard-FW, OTA-Tests, UART-MitM, LKS32-Datasheet-Analyse) ist klar: der einzige übrig gebliebene Pfad für die Speed-Limit-Entfernung ist ein **direkter Hardware-Eingriff auf den BLDC-Controller**. Alle Software-only-Pfade sind tot.

## Ausgeschlossene Pfade (nicht mehr weiter verfolgen)

| Pfad | Warum tot |
|---|---|
| BLE-Command-Manipulation (CMD 0x6E, 0x6B) | Controller ignoriert, Limit ist in Controller-FW |
| OTA-Patching der Meter-FW | 2. Validator im PATCH-Image rejected jede Modifikation (Meter-FW hat ohnehin keinen Einfluss auf Speed) |
| BLDC-FW via BLE OTA | Dashboard hat kein `dfu_start 2`-Handler und kein UART-XMODEM-Relay zum Controller (36+ Sessions, 0 ACKs) |
| UART-ISP auf LKS32MC081 | Datasheet v1.93 bestätigt: **kein UART-Bootloader existiert**. Flash-Programming ausschließlich via SWD. |
| Yellow-Wire-MitM + Dashboard-Ersatz | Controller ignoriert manipulierte Speed-Bytes, enforced internes Limit |
| Meter-FW mit BLDC-Relay-Code patchen | Wertlos selbst wenn gelungen, weil LKS32 kein UART-ISP hat |

## Verbleibende Pfade — ranked

| # | Pfad | Erfolg | Zeit | Kosten |
|---|---|---|---|---|
| **1** | **Controller-Tausch Global-Variante** | **~60 %** | 2-4 h + Lieferzeit | 30-50 € |
| **2** | **SWD-Flash via ST-Link v2 auf LKS32MC081** | **~40 %** | 2-8 h | ~10 € |
| **3** | **Kombiniert — erst SWD, bei Misserfolg Controller-Tausch** | **~75 %** | 4-12 h | 10-50 € |
| 4 | VESC Open-Source Controller einbauen | ~30 % | 10-20 h | 100-200 € |
| 5 | US-Account + VPN für US-Firmware-Download | ~10 % | 2-4 h | ~5 € |
| 6 | Glitching-Attack auf LKS32 SWD (nur falls Protection aktiv) | ~20 % | 40-80 h | 400 € + |

## Empfohlener Weg (Pfad 3: kombiniert)

### Phase A — SWD versuchen (2-4 h Arbeit, ~10 €)

**Vorbedingungen:**
- ST-Link v2 Clone (AliExpress 3-7 €) oder bereits vorhandenes ARM-Debug-Probe
- pyocd oder openocd installiert (`pip3 install --user pyocd`)
- Mikroskop oder starke Lupe + Seitenlicht
- Drei Jumper-Drähte + feiner Lötkolben

**Schritte:**
1. ESC-Board aus dem Scooter ausbauen (Akku vorher abklemmen!)
2. LKS32MC081-MCU lokalisieren (schwarzes TQFP48-Package, ~7 × 7 mm)
3. Pin 1 des MCU identifizieren (Punkt-Markierung am Chip), dann Pin 2 / 47 / 48 zählen
4. Traces von diesen drei Pins auf der PCB verfolgen — Resin ist transparent, mit Seitenlicht sichtbar
5. Trace-Endpunkte als Test-Pads oder Vias identifizieren
6. Jumper-Drähte an die drei Pads anlöten (GND separat vom Akku-Minus holen)
7. ST-Link v2 verbinden: GND / SWDIO (Pin 48) / SWCLK (Pin 47), RESET optional
8. Akku anklemmen, Scooter NICHT einschalten
9. `pyocd list --probes` → Probe gefunden?
10. `pyocd cmd -t cortex_m` → `reg` versuchen, dann `--connect=under-reset` falls nötig
11. Bei Erfolg: `pyocd cmd --flash-read dump.bin 0 65536` für den 64 KB Full-Dump

**Stop-Gate:** Wenn nach 2-4 h keine SWD-Pads auffindbar oder Connect nicht herstellbar → Phase B.

### Phase B — Controller-Tausch (2-4 h, 30-50 €)

**Beschaffung:**
- AliExpress-Suche: `"Navee ST3 Global controller"`, `"Brightway BLDC controller"`, `"LKS32MC081 scooter ESC"`
- Alternativ: `pid=24012` als Identifikator angeben
- Prüfen ob Connector-Typ (Motor-Phasen 3-Pin gelb, Hall-Sensor 5-Pin, Dashboard-Cable) zum vorhandenen passt

**Einbau:**
1. Scooter öffnen (Schrauben unter Deck-Abdeckung)
2. Akku abklemmen, 5 Min warten (Kondensatoren entladen)
3. Alten Controller: Motor-Phasen (gelb 3-Pin), Hall-Sensor (5-Pin), Dashboard-Kabel (5-Pin), Akku-Leitungen abziehen
4. Neuen Controller einsetzen, gleiche Verbindungen in gleicher Reihenfolge stecken
5. Akku anklemmen, Scooter einschalten
6. Funktionstest auf der Stelle (Rad hoch, kurzer Gas-Test)
7. Wenn alles OK: zusammenschrauben, Probefahrt

## Was wir für Phase A noch brauchen

**Konkrete Pad-Lokalisierung:** Ein scharfes Makro-Foto nur vom LKS32-MCU-Bereich (mit ~15 mm Umgebung, bei Seitenlicht, scharf auf der Platinenoberfläche) ermöglicht Trace-Analyse. Ohne dieses Foto ist Phase A „blindes Stochern".

## Realistische Gesamt-Einschätzung

- Wer **pragmatisch** schnell 30 km/h haben will: Pfad 1 (reiner Controller-Tausch) — in 3-4 Tagen erledigt inkl. Versand.
- Wer den **Software-/SWD-Weg** für die Lernerfahrung und die Repo-Dokumentation gehen will: Pfad 2/3 — riskanter, aber Brickrisiko kontrollierbar (Original-Controller als Backup behalten).

**Gesamt-Wahrscheinlichkeit für Speed-Limit-Bypass bei Pfad 3: ~75 %.**

## Referenzen (alles im Repo)

- `docs/STATUS.md` — empirische Pass/Fail-Matrix
- `docs/HARDWARE.md` — MCU- und Pinout-Fakten
- `docs/LKS32MC081.md` — Datasheet-Extrakt (SWD, Protection, Programming)
- `docs/LKS32MC08x_Datasheet_EN_v1.93.pdf` — Original-Datasheet
- `docs/SECURE_ELEMENT.md` — Apple-FMNA-Funde im Dashboard
- `docs/PROTOCOL.md` — BLE- und UART-Protokoll-Referenz

---

**Dieses Dokument ist die einzige noch umsetzbare Roadmap. Wenn sie durchgearbeitet ist und keiner der Pfade zum Ziel führt, ist das Projekt aus Software-Sicht erschöpft.**
