# Reverse Engineering — Navee ST3 Pro

Dokumentation des Reverse-Engineering-Prozesses und der Erkenntnisse zum Navee ST3 Pro E-Scooter.

---

## Inhaltsverzeichnis

- [Methodik](#methodik)
- [APK-Dekompilierung](#apk-dekompilierung)
- [BT-HCI-Capture Analyse](#bt-hci-capture-analyse)
- [Erkenntnisse](#erkenntnisse)
- [Server-API Endpoints](#server-api-endpoints)
- [OTA Firmware-Update Mechanismus](#ota-firmware-update-mechanismus)
- [Ghidra-Analyse Ergebnisse](#ghidra-analyse-ergebnisse-detailliert)

---

## Methodik

Drei Analysemethoden wurden kombiniert:

1. **APK-Dekompilierung** — Statische Analyse der offiziellen Navee-App
2. **BT-HCI-Capture** — Mitschnitt der BLE-Kommunikation zwischen offizieller App und Scooter
3. **Live-Tests** — Senden von Kommandos an den Scooter und Auswerten der Responses

---

## APK-Dekompilierung

### Tools

- **jadx** — Dekompilierung der APK zu Java-Quellcode
- **apktool** — Extraktion von Resources und Manifest

### Vorgehensweise

```bash
# APK dekompilieren
jadx -d navee-decompiled/ com.navee.app.apk

# Alternativ nur Resources
apktool d com.navee.app.apk -o navee-resources/
```

### Relevante Quellcode-Dateien

Die folgenden Klassen in der dekompilierten APK enthalten die Protokoll-Implementierung:

| Datei (obfuskiert) | Inhalt |
|--------------------|--------|
| `b4/a.java` | BLE-Kommunikationsschicht — Frame-Encoding/Decoding, Checksum-Berechnung |
| `b4/b.java` | Kommando-Definitionen und Payload-Builder |
| `b4/c.java` | Authentifizierungs-Logik (AES-128-ECB, Key-Array) |
| `d3/a.java` | Telemetrie-Parser (0x90, 0x91, 0x92) |
| `d3/b.java` | Status-Response Parser (0x70, 0x72) |
| `e5/a.java` | PID-Erkennung und Speed-Optionen-Mapping |
| `f2/a.java` | OTA-Update Logik (XMODEM) |

### Wichtige Fundstellen

**AES-Schlüssel** (in `b4/c.java`):
```java
private static final String[] AUTH_KEYS = {
    "NaveeAUTHKEY001!",
    "NaveeAUTHKEY002!",
    "NaveeAUTHKEY003!",
    "NaveeAUTHKEY004!",
    "NaveeAUTHKEY005!"
};
```

**PID-Speed-Mapping** (in `e5/a.java`):
```java
// PID 23452 (DE)
case 23452:
    ecoSpeeds = new int[]{6, 10, 15, 20};
    sportSpeeds = new int[]{6, 10, 15, 20, 22};
    maxSpeed = 22;
    break;
```

**Frame-Konstanten** (in `b4/a.java`):
```java
static final byte[] HEADER = {0x55, (byte)0xAA};
static final byte[] FOOTER = {(byte)0xFE, (byte)0xFD};
```

---

## BT-HCI-Capture Analyse

### Aufzeichnung

1. BT-HCI-Snoop-Logging auf dem Android-Gerät aktivieren
2. Offizielle Navee-App starten und mit dem Scooter verbinden
3. Verschiedene Aktionen ausführen (Licht ein/aus, Modus wechseln, etc.)
4. HCI-Log via `adb bugreport` exportieren

### Analyse in Wireshark

Nützliche Wireshark-Filter:

```
# Alle BLE-Writes an den Scooter
btatt.opcode == 0x12 && btatt.handle == 0x0012

# Alle Notifications vom Scooter
btatt.opcode == 0x1b && btatt.handle == 0x0014

# Nur Auth-Pakete
btatt.value[2:1] == 30 || btatt.value[2:1] == 31
```

### Bestätigt durch Capture

Die folgenden Kommandos wurden durch BT-Captures verifiziert:

| Kommando | Capture-Verifizierung |
|----------|-----------------------|
| `0x57` Auto-Headlight | Lichtsensor ein/aus — Front- und Rücklicht gekoppelt |
| `0x54` Taillight | Separates Rücklicht (bei diesem Modell mit Frontlicht gekoppelt) |
| `0x60` Turn Sound | **Blinker-Ton**, nicht Rücklicht! (häufiger RE-Fehler) |
| `0x5F` TCS | Traktionskontrolle ein/aus |
| `0x53` ERS | Rekuperation — Werte 30/60/90 |
| `0x58` Speed Mode | ECO (0x03) / SPORT (0x05) |
| `0x30` Auth | Auth-Sequenz beim App-Start inkl. Device ID |
| `0x6F` Post-Auth | Parameter-Übertragung direkt nach erfolgreicher Auth |
| `0x70` Status | Periodisch alle ~2s von der App angefragt |
| `0x90` HomePage | Batterie, Restreichweite, Spannung (~1s Intervall) |
| `0x92` DrivePage | Geschwindigkeit, Distanz, Trip (~1s Intervall) |

---

## Erkenntnisse — Chronologie der Speed-Unlock-Versuche

### Ansatz 1: BLE-Protokoll (❌ gescheitert)

**Idee:** Das BLE-Kommando `0x6E` (Set Max Speed) nutzen, um das Limit von 22 km/h zu erhöhen.

**Vorgehen:**
1. Offizielle Navee APK dekompiliert → Kommando `0x6E` mit Daten `[0x01, km/h]` identifiziert
2. BLE-Auth implementiert (AES-128-ECB, Device-ID aus BT-Capture)
3. Auth erfolgreich, Kommando gesendet, Scooter antwortet mit ACK

**Ergebnis:** Kommando wird **syntaktisch akzeptiert** (ACK), aber der Wert in Byte 26 der Status-Response (`0x16` = 22 km/h) **ändert sich nicht**. Das Limit ist per BLE nicht modifizierbar.

---

### Ansatz 2: UART Man-in-the-Middle (❌ gescheitert)

**Idee:** Das Dashboard sendet Speed-Limits über UART an den Motor-Controller (Frame A, Bytes 6-7). Ein Arduino zwischen Dashboard und Controller könnte diese Werte manipulieren.

**Vorgehen:**
1. UART-Schnittstelle am Dashboard-Stecker identifiziert (grüne Ader, 19200 Baud, 8N1)
2. Drei Frame-Typen reverse-engineered (siehe [INTERNAL_UART_PROTOCOL.md](INTERNAL_UART_PROTOCOL.md))
3. Speed-Limit-Kandidaten in Frame A Bytes 6-7 lokalisiert (`0x17`=23, `0x15`=21)
4. Arduino Nano MitM gebaut: Frames abfangen, Bytes 6-7 auf `0x1E`/`0x1E` (30/30) ändern, Checksum neu berechnen

**Verkabelung:**
```
Dashboard (grüne Ader durchtrennen!)
    └──→ Arduino D2 (SoftSerial RX)
         Arduino D3 (SoftSerial TX)
              └──→ Controller

Scooter GND (schwarz) ──→ Arduino GND
Arduino USB ──→ PC (Stromversorgung + Debug)
```

**Implementierung:** [`/reverse-engineering/navee_uart_mitm_nano/navee_uart_mitm_nano.ino`](../reverse-engineering/navee_uart_mitm_nano/navee_uart_mitm_nano.ino)

**Ergebnis:**
- ~2000+ Frames erfolgreich manipuliert (Checksum korrekt, Controller akzeptiert syntaktisch)
- Realer Fahrtest: **Geschwindigkeit bleibt bei 22 km/h**
- Der Motor-Controller **ignoriert die UART-Speed-Werte komplett**
- Frame A Bytes 6/7 sind nur Logging-/Anzeige-Werte ohne sicherheitskritische Funktion

**Fazit:** Das Speed-Limit ist **im Controller-Firmware-Code hardcoded**, nicht vom Dashboard steuerbar.

---

### Ansatz 3: Firmware-Patching (✅ erfolgreich)

**Idee:** Die Meter-Firmware (Dashboard-Controller) direkt patchen und per OTA flashen.

**Vorgehen:**
1. Firmware-Binary über die Navee Server-API heruntergeladen (`tools/firmware_grabber.py`)
2. API: `POST https://lj.naveetech.com/tundra-api/vehicle/modelSoftware` mit `vehicleModelId=3801`
3. Login mit `imgCode=""` (leerer Captcha-Code funktioniert!)
4. Meter-Firmware v2.0.3.1 (135 KB, ARM Thumb Code) analysiert

**Kritische Funde in der Meter-Firmware:**
```
Offset 0x12E93: "speed limit %d"        ← Speed-Limit als printf-Variable!
Offset 0x13705: "st_speed_limit = %d"   ← Struct-Member-Name
Offset 0x13041: "s max speed state"
Offset 0x130CA: "reading speed set info"
```

**Bedeutung:** Das Speed-Limit ist eine **Laufzeit-Variable** (`st_speed_limit`) in einem Struct, nicht ein einfacher hardcodierter Wert. Es wird beim Boot basierend auf der PID gesetzt. Durch Patchen des Initialisierungswertes oder der PID-Prüfung in der Firmware kann das Limit geändert werden.

**Firmware-Header-Format:**
```
Offset 0x00: Modell-String "T22020" (Meter) / "T24180" (BMS)
Offset 0x06: Typ-Byte (0x01=Meter, 0x03=BMS)
Offset 0x07: Version-String "00030001"
Offset 0x10: Code-Start-Offset + Größe
Ab ~0x100:   ARM Thumb Maschinencode (Cortex-M, nach FF-Padding)
```

**Verfügbare Firmware (Stand März 2026):**

| Komponente | Version | Größe | Beschreibung |
|-----------|---------|-------|--------------|
| **Meter** (Dashboard) | 2.0.3.1 | 135 KB | ARM Thumb, enthält Speed-Limit-Logik |
| **BMS** (Batterie) | 1.0.0.4 | 24 KB | Batterie-Management, keine Speed-Daten |

### Ghidra-Analyse Ergebnisse (detailliert)

Die Ghidra-Analyse der Meter-Firmware (navee_meter_v2.0.3.1.bin, 138240 Bytes, ARM Cortex-M Thumb) hat den vollständigen Speed-Limit-Mechanismus offengelegt.

#### Speed-Lookup Funktion (FUN_0800ad02)

Dies ist DIE kritische Funktion. Sie bestimmt das tatsächliche Speed-Limit, das an den Motor-Controller gesendet wird:

```c
int FUN_0800ad02(int param_1) {
    if (param_1 == 1) return 0x69;              // 10.5 km/h (Walk-Modus)
    if (sys_stc[0x4a] == 0x02) {                // lift_speed_limit FLAG
        return sys_stc[0x47] * 10 + 5;          // BENUTZERDEFINIERTE GESCHWINDIGKEIT!
    }
    switch(area_code) {                          // PID-basierte Standardwerte
        case 3: if (mode==2) return 0x9b;        // 15.5 km/h
                if (mode==3||5) return 0xe1;     // 22.5 km/h ← DE LIMIT
        case 4: if (mode==2) return 0x9b;        // 15.5
                if (mode==3||5) return 0xff;     // 25.5 km/h
        case 5: if (mode==2) return 0x9b;        // 15.5
                if (mode==3||5) return 0xff;     // 25.5
        case 6,7: if (mode==2) return 0xcd;      // 20.5
                  if (mode==3||5) return 0x145;  // 32.5 km/h
                  if (mode==4) return 0x195;     // 40.5 km/h
    }
}
```

Speed-Werte in internen Einheiten (÷10 für km/h, +0.5):

| Hex | Dezimal | km/h |
|-----|---------|------|
| 0x69 | 105 | 10.5 (Walk) |
| 0x9B | 155 | 15.5 |
| 0xCD | 205 | 20.5 |
| 0xE1 | 225 | 22.5 (DE!) |
| 0xFF | 255 | 25.5 |
| 0x145 | 325 | 32.5 |
| 0x195 | 405 | 40.5 |

#### Speed-Limit Setter (FUN_080109ae)

BLE CMD 0x6E ruft diese Funktion auf:

```c
void FUN_080109ae(char *param_1) {
    if (*param_1 == 0x01) {
        sys_stc[0x47] = param_1[1];     // Speed-Wert direkt schreiben
        notify_change();
        save_to_flash();                 // FUN_08012cc8 - persistent!
    }
}
```

Der BLE-Command FUNKTIONIERT — der Wert wird geschrieben und im Flash gespeichert. Aber er wird nur verwendet wenn das `lift_speed_limit` Flag (`sys_stc[0x4a]`) auf `0x02` steht.

#### Das lift_speed_limit Flag (sys_stc + 0x4a)

Gesetzt in FUN_0800f9d0 bei File Offset 0xF848:

```asm
0800f846: cmp r5,#0xa        ; r5 <= 10?
0800f848: bls 0x0800f850     ; JA → Standard-Modus (PID-Default)
0800f84a: strb r3,[r1,#0x4a] ; NEIN → Custom-Modus (lift!)
...
0800f850: strb r2,[r1,#0x4a] ; Standard-Modus
```

#### Der Patch (1 Byte)

| | File Offset | Bytes | Instruktion | Effekt |
|---|------------|-------|-------------|--------|
| Original | 0xF848 | 02 D9 | bls (Custom überspringen) | PID-Default (22 km/h) |
| Gepatcht | 0xF848 | 00 BF | NOP | Custom Speed via BLE 0x6E |

Der NOP lässt den Code zur nächsten Instruktion durchfallen (`strb r3,[r1,#0x4a]`), die das `lift_speed_limit` Flag auf den Custom-Wert setzt. Danach bestimmt `sys_stc[0x47]` (setzbar via BLE CMD 0x6E) die Geschwindigkeit.

#### Flash-Prozedur

1. Original-Firmware flashen (OTA-Test)
2. Gepatchte Firmware flashen
3. Speed via BLE CMD 0x6E setzen: `[0x01, gewünschte_kmh]`
4. Rollback jederzeit möglich durch erneutes Flashen der Original-Firmware

#### Wichtige Architektur-Erkenntnis

- Das Speed-Limit wird in der **Meter-Firmware** (Dashboard) berechnet
- Der Wert wird über UART Frame A an den Motor-Controller gesendet
- Der Motor-Controller AKZEPTIERT den Wert vom Dashboard (anders als beim UART-MitM, wo die Manipulation vom Arduino kam)
- Der Unterschied: beim MitM wurde der Frame A manipuliert NACHDEM das Dashboard ihn gesendet hat. Mit der gepatchten Firmware sendet das Dashboard selbst den höheren Wert — der Controller akzeptiert ihn als authentisch

---

### Zusammenfassung Speed-Limit-Architektur

```
┌──────────────────────────────────────────────────────────────┐
│                     SPEED-LIMIT CHAIN                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Ansatz 1:                                                   │
│  BLE App (0x6E)  ──→  ACK'd aber ignoriert              ❌  │
│                       (lift_speed_limit Flag steht nicht)     │
│                                                              │
│  Ansatz 2:                                                   │
│  UART Frame A    ──→  Bytes 6/7 manipuliert,             ❌  │
│  (Arduino MitM)       Controller ignoriert externe           │
│                       Manipulation der Frames                │
│                                                              │
│  Ansatz 3:                                                   │
│  Firmware-Patch  ──→  1 Byte NOP (0xF848: 02 D9→00 BF)  ✅  │
│  (Meter OTA)          Aktiviert lift_speed_limit Flag,       │
│                       danach setzt BLE 0x6E den Wert.        │
│                       Dashboard sendet authentischen          │
│                       Speed-Wert über UART Frame A           │
│                       → Controller akzeptiert!               │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  Warum Ansatz 3 funktioniert, Ansatz 2 aber nicht:  │     │
│  │                                                     │     │
│  │  MitM:    Dashboard ──→ [Arduino ändert] ──→ Ctrl   │     │
│  │           Controller erkennt externe Manipulation   │     │
│  │                                                     │     │
│  │  Patch:   Dashboard (gepatcht) ──→ Ctrl             │     │
│  │           Dashboard sendet SELBST den höheren Wert  │     │
│  │           → Controller akzeptiert als authentisch    │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Protokoll-Stabilität

- Das BLE-Protokoll ist stabil und deterministisch
- Gleiche Kommandos erzeugen immer die gleichen Ergebnisse
- Keine Zeitabhängigkeiten außer der initialen Auth

### Authentifizierung

- Die einfache Auth (CMD `0x30`) ist für den DE-Markt ausreichend
- Challenge-Response (CMD `0x31`) ist implementiert, wird aber nicht erzwungen
- Alle 5 AES-Schlüssel funktionieren — der Key-Index scheint beliebig wählbar

---

## Server-API Endpoints

Bei der APK-Analyse wurden folgende Server-Endpunkte identifiziert:

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `https://api.navee.com/api/v1/user/login` | POST | Benutzer-Login |
| `https://api.navee.com/api/v1/user/info` | GET | Benutzer-Informationen |
| `https://api.navee.com/api/v1/device/bind` | POST | Gerät an Account binden |
| `https://api.navee.com/api/v1/device/unbind` | POST | Gerät-Bindung lösen |
| `https://api.navee.com/api/v1/device/info` | GET | Geräte-Informationen |
| `https://api.navee.com/api/v1/device/list` | GET | Liste gebundener Geräte |
| `https://api.navee.com/api/v1/firmware/check` | GET | Firmware-Update prüfen |
| `https://api.navee.com/api/v1/firmware/download` | GET | Firmware herunterladen |
| `https://api.navee.com/api/v1/ride/history` | GET | Fahrtenverlauf |
| `https://api.navee.com/api/v1/ride/statistics` | GET | Fahrstatistiken |

> **Hinweis:** Diese Endpoints wurden durch statische Analyse gefunden. Die tatsächliche API-Struktur kann abweichen. Dieses Projekt nutzt **keine** Server-APIs — alle Kommunikation erfolgt direkt über BLE.

---

## OTA Firmware-Update Mechanismus

Die Firmware-Update-Funktion wurde in der APK identifiziert, wird von diesem Projekt aber **nicht implementiert**.

### Ablauf (aus APK-Analyse)

1. **Update prüfen:** App fragt Server-API nach verfügbarem Update
2. **Firmware herunterladen:** Binärdatei vom Server laden
3. **BLE-Transfer:** Firmware wird via **XMODEM-Protokoll** über BLE übertragen
4. **Verifikation:** Scooter verifiziert die Firmware-Integrität
5. **Installation:** Scooter installiert das Update und startet neu

### XMODEM-Details

- Blockgröße: 128 Bytes
- Prüfsumme: CRC-16
- Übertragung über die gleiche BLE-Characteristic wie normale Kommandos
- Spezieller OTA-Modus wird vor der Übertragung aktiviert

> **Warnung:** Firmware-Updates sind riskant und können den Scooter unbrauchbar machen. Dieses Projekt implementiert **keine** OTA-Update-Funktionalität.

---

## Hardware Reverse Engineering — UART-Schnittstelle

### Dashboard-Stecker Pinbelegung

Am Dashboard-Kabelbaum des ST3 Pro wurde ein Stecker mit 5 Adern identifiziert. Die Spannungsmessung (Multimeter gegen GND) ergab:

| Ader | Farbe | Spannung | Funktion |
|------|-------|----------|----------|
| 1 | Schwarz | 0 V | **GND** |
| 2 | Rot | 53,04 V | VCC Akku (direkt, **nicht anfassen!**) |
| 3 | Blau | 52,2 V | VCC Akku/Dashboard-Versorgung |
| 4 | Gelb | 3,76 V (Idle) | **UART Signal** — 3.3V Logik, Idle-High |
| 5 | Grün | 4,12 V (Idle) | **UART Signal** — 3.3V/5V Logik, Idle-High |

### Interpretation

- **Gelb und Grün** sind UART TX/RX-Kandidaten. Idle-High bei 3,3–4,1 V passt zu Standard-UART-Logikpegeln.
- **Rot und Blau** führen volle Akkuspannung (~52–53 V). Diese Leitungen **niemals** direkt an Mikrocontroller oder UART-Adapter anschließen!
- Die genaue Zuordnung TX/RX (welche Leitung sendet, welche empfängt) muss noch ermittelt werden.

### Ergebnis der UART-Analyse

- **Gelb:** Kein UART-Signal — unbekanntes Signal
- **Grün:** UART TX (Controller → Dashboard), **19200 Baud**, 8N1
- Protokoll nutzt ein **komplett anderes Frame-Format** als BLE (kein `55 AA`)
- Drei Frame-Typen identifiziert (Dashboard-Status, Telemetrie, Controller-Telemetrie)
- **Keine Authentifizierung** nötig — direkter Hardware-Zugriff

→ Vollständige Dokumentation: [INTERNAL_UART_PROTOCOL.md](INTERNAL_UART_PROTOCOL.md)

### Vergleich BLE ↔ UART

| Eigenschaft | BLE-Protokoll | UART-Protokoll |
|-------------|---------------|----------------|
| Frame-Header | `55 AA` | Komplement-Paarung (`0x61/0x9E`, `0x64/0x9B`) |
| Auth erforderlich | Ja (AES-128, Device-ID) | **Nein** |
| ECO-Modus | `0x03` | `0x35` |
| SPORT-Modus | `0x05` | `0x33` |
| Licht AN | `0x01` | `0x04` |
| Batterie % | 0x90 data[3] = `0x64` (100%) | Frame C byte 15 = `0x64` (100%) ✅ |
| Spannung | 0x90 bytes 9-12 = 52944 mV | Frame C bytes 5-6 = 1275 (÷25 ≈ 51V) ✅ |
| Speed-Limit | 0x70 byte 26 = `0x16` (22), **read-only** | Frame A bytes 6-7 = `0x17`/`0x15`, **vom Dashboard gesendet!** |

### Kritische Erkenntnis: Speed-Limit über UART

Das BLE-Protokoll meldet 22 km/h als unveränderliches Firmware-Limit (CMD `0x6E` wird ACK'd aber ignoriert). Über UART wurde entdeckt, dass das **Dashboard die Speed-Limits aktiv an den Controller sendet** (Frame A, Bytes 6-7). Ein Arduino/ESP32 als Man-in-the-Middle kann diese Werte abfangen und modifizieren.

#### UART Man-in-the-Middle Speed Unlock

**Status:** Getestet mit Arduino Nano, funktionsfähige Implementierung vorhanden

**Verkabelung:**
```
Dashboard (grüne Ader durchtrennen!)
    └──→ Arduino D2 (SoftSerial RX)
         Arduino D3 (SoftSerial TX)
              └──→ Controller

Scooter GND (schwarz) ──→ Arduino GND
Arduino USB ──→ PC (Stromversorgung + Debug)
```

**Funktionsweise:**
1. Arduino sitzt zwischen Dashboard und Controller auf der UART-Leitung
2. Frame A wird abgefangen (Header `0x61`, CMD `0x30`)
3. Bytes 6-7 (Speed-Limits) werden von `0x17`/`0x16` (23/22 km/h) auf z.B. `0x1E`/`0x1E` (30/30 km/h) geändert
4. Checksum wird neu berechnet
5. Modifizierter Frame wird an Controller weitergeleitet

**Implementierung:** `/reverse-engineering/navee_uart_mitm_nano/navee_uart_mitm_nano.ino`

**Ergebnis:** 
- Dashboard sendet kontinuierlich modifizierte Speed-Limits an Controller
- ~2000+ Frames erfolgreich manipuliert in Tests
- Controller akzeptiert die neuen Werte syntaktisch (Checksum OK)

**Testergebnis (März 2026):** Nach realem Fahrtest mit über 1000 erfolgreich manipulierten Frames stellte sich heraus, dass **der Controller die UART-Speed-Limits komplett ignoriert**. Die Geschwindigkeit blieb trotz erfolgreicher Manipulation bei 22 km/h. 

**Fazit:** Die Speed-Limits sind firmware-seitig im Controller hardcoded und unabhängig von Dashboard-Commands. Frame A Bytes 6/7 sind lediglich Logging-/Anzeige-Werte ohne sicherheitskritische Funktion.

#### Ergebnis

Der Firmware-Patch-Ansatz (Ansatz 3) war **erfolgreich**. Siehe oben: [Ghidra-Analyse Ergebnisse](#ghidra-analyse-ergebnisse-detailliert) für die vollständige technische Dokumentation des 1-Byte-Patches.

---

## Firmware-Download & Analyse

### API-Zugang

Firmware-Binaries können über die Navee Server-API heruntergeladen werden:

```bash
python3 tools/firmware_grabber.py
```

**API-Details:**
- Base URL: `https://lj.naveetech.com/tundra-api`
- Login: `POST /login` mit `email`, `passwd`, `imgCode` (kann leer sein!)
- Modelle: `GET /vehicle/model` → ST3 PRO hat `vehicleModelId=3801`, `pid=23452`
- Firmware: `POST /vehicle/modelSoftware` mit `vehicleModelId` + alte Versionsstrings

### Verfügbare Firmware-Komponenten (Stand März 2026)

| Komponente | Version | Größe | Beschreibung |
|-----------|---------|-------|--------------|
| **Meter** (Dashboard) | 2.0.3.1 | 135 KB | ARM Thumb Code, enthält Speed-Limit-Logik |
| **BMS** (Batterie) | 1.0.0.4 | 24 KB | Batterie-Management, keine Speed-Daten |

### Firmware-Header-Format

```
Offset 0x00: Modell-String (z.B. "T22020" für Meter, "T24180" für BMS)
Offset 0x06: Typ-Byte (0x01=Meter, 0x03=BMS)
Offset 0x07: Version-String (z.B. "00030001")
Offset 0x10: Code-Start-Offset + Größe
Ab ~0x100:   ARM Thumb Maschinencode (nach FF-Padding)
```

### Analyse-Ergebnisse: Meter-Firmware

Die Meter-Firmware (Dashboard-Controller) enthält die Speed-Limit-Logik:

**Gefundene Strings:**
```
"reading speed info"
"reading speed set info"
"s max speed state"
"speed limit %d"            ← Speed-Limit als Variable!
"st_speed_limit = %d"       ← Struct-Member
"NAVEE"
"NAVEE - Find"
```

**Bedeutung:** Das Speed-Limit ist eine **Variable** (`st_speed_limit`), kein hardcodierter Wert. Es wird zur Laufzeit gesetzt — vermutlich basierend auf der PID. Durch Patchen der Firmware könnte der Initialisierungswert geändert werden.

### Firmware-RE Ergebnisse

Alle Schritte der Firmware-Analyse wurden abgeschlossen:

1. **ARM Thumb Disassemblierung** — Ghidra mit Cortex-M Profil ✅
2. **`st_speed_limit` Referenzen** — Speed-Lookup in FUN_0800ad02 gefunden ✅
3. **PID-Check lokalisiert** — area_code Switch in FUN_0800ad02, lift_speed_limit Flag in FUN_0800f9d0 ✅
4. **Patch erstellt** — 1-Byte NOP bei File Offset 0xF848 (02 D9 → 00 BF) ✅
5. **OTA-Flash** — Über BLE XMODEM (128-Byte Blöcke, CRC-16) ✅

### Sicherheitshinweise

> **Achtung:** Die Akku-Leitungen (Rot/Blau) führen **53 V DC**. Kurzschluss oder Berührung mit Logik-Bauteilen zerstört sofort den Mikrocontroller und kann zu Bränden führen. Nur die Signalleitungen (Gelb/Grün) und GND (Schwarz) verwenden!

> **UART-Adapter:** Einen 3.3V-kompatiblen USB-UART-Adapter verwenden (z.B. CP2102, FT232RL, CH340). **Keine 5V-Adapter direkt anschließen** falls die Logik 3.3V ist — vorher mit Oszilloskop/Multimeter verifizieren.

---

## Siehe auch

- [PROTOCOL.md](PROTOCOL.md) — Vollständige Protokoll-Referenz
- [AUTHENTICATION.md](AUTHENTICATION.md) — Authentifizierungsablauf
