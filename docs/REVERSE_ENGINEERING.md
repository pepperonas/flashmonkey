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
| `0x57` Headlight | Gesendet beim Antippen des Licht-Buttons in der offiziellen App |
| `0x60` Taillight | Gesendet beim Antippen des Rücklicht-Buttons |
| `0x30` Auth | Auth-Sequenz beim App-Start inkl. Device ID |
| `0x70` Status | Periodisch alle ~2s von der App angefragt |
| `0x90` Telemetrie | Kontinuierlich vom Scooter gesendet (~1s Intervall) |

---

## Erkenntnisse

### 22 km/h Firmware-Limit (DE-Markt)

Die wichtigste Erkenntnis des Reverse Engineering:

- Der Navee ST3 Pro mit **PID 23452** (DE-Markt) hat ein **firmware-seitiges Hard-Limit** von **22 km/h**
- Dieses Limit ist in Byte 26 der Status-Response (`0x70`) sichtbar als `0x16`
- Der Befehl `0x6E` (Max Speed setzen) wird vom Scooter zwar mit ACK bestätigt, **ändert aber den Wert nicht**
- Die Speed-Optionen in der offiziellen App sind PID-abhängig und überschreiten nie das Firmware-Limit
- Eine Änderung der Höchstgeschwindigkeit wäre nur durch ein **Firmware-Update** möglich (nicht Ziel dieses Projekts)

### Protokoll-Stabilität

- Das BLE-Protokoll ist stabil und deterministisch
- Gleiche Kommandos erzeugen immer die gleichen Ergebnisse
- Der Scooter antwortet auf unbekannte Kommandos mit einem generischen NACK
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

## Siehe auch

- [PROTOCOL.md](PROTOCOL.md) — Vollständige Protokoll-Referenz
- [AUTHENTICATION.md](AUTHENTICATION.md) — Authentifizierungsablauf
