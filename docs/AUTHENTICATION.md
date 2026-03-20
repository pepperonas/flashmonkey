[English](AUTHENTICATION.md) | [Deutsch](AUTHENTICATION_DE.md)

# Authentifizierung — Navee ST3 Pro

Dokumentation des BLE-Authentifizierungsablaufs für den Navee ST3 Pro E-Scooter.

---

## Inhaltsverzeichnis

- [Übersicht](#uebersicht)
- [AES-128-ECB Schlüssel](#aes-128-ecb-schluessel)
- [Einfache Authentifizierung](#einfache-authentifizierung)
- [Challenge-Response Authentifizierung](#challenge-response-authentifizierung)
- [Device ID](#device-id)
- [Device ID aus BT-Capture extrahieren](#device-id-aus-bt-capture-extrahieren)

---

## Übersicht

Der Navee ST3 Pro verwendet eine AES-128-ECB basierte Authentifizierung mit 5 fest kodierten Schlüsseln. Für die meisten Firmware-Versionen (einschließlich PID 23452 / DE-Markt) genügt die **einfache Authentifizierung** (CMD `0x30`). Die vollständige Challenge-Response Authentifizierung (CMD `0x31`) ist im Firmware-Code vorhanden, wird aber aktuell nicht erzwungen.

---

## AES-128-ECB Schlüssel

Die folgenden 5 Schlüssel sind in der offiziellen Navee-APK fest kodiert und werden für die Verschlüsselung der Auth-Payload verwendet:

| Index | Schlüssel (Hex) |
|-------|-----------------|
| 0 | `4E 61 76 65 65 41 55 54 48 4B 45 59 30 30 31 21` |
| 1 | `4E 61 76 65 65 41 55 54 48 4B 45 59 30 30 32 21` |
| 2 | `4E 61 76 65 65 41 55 54 48 4B 45 59 30 30 33 21` |
| 3 | `4E 61 76 65 65 41 55 54 48 4B 45 59 30 30 34 21` |
| 4 | `4E 61 76 65 65 41 55 54 48 4B 45 59 30 30 35 21` |

Im ASCII-Klartext:

| Index | Schlüssel (ASCII) |
|-------|-------------------|
| 0 | `NaveeAUTHKEY001!` |
| 1 | `NaveeAUTHKEY002!` |
| 2 | `NaveeAUTHKEY003!` |
| 3 | `NaveeAUTHKEY004!` |
| 4 | `NaveeAUTHKEY005!` |

Alle Schlüssel sind exakt 16 Bytes lang (128 Bit), passend für AES-128.

---

## Einfache Authentifizierung

Die einfache Auth ist der primäre Mechanismus für den ST3 Pro (PID 23452). Ablauf:

### Schritt 1: Auth Request senden (CMD `0x30`)

Payload-Aufbau:

```
[keyIndex, 0x00, deviceId[0], deviceId[1], deviceId[2],
 deviceId[3], deviceId[4], deviceId[5], 0x00]
```

| Feld | Länge | Beschreibung |
|------|--------|--------------|
| `keyIndex` | 1 Byte | Index des verwendeten AES-Schlüssels (0-4) |
| `0x00` | 1 Byte | Padding |
| `deviceId` | 6 Bytes | Geräte-ID des Nutzers (Navee-Account-ID) |
| `0x00` | 1 Byte | Padding |

Gesamtlänge DATA: **9 Bytes**

### Schritt 2: Response auswerten

Die Antwort kommt auf der Notify-Characteristic mit CMD `0x30`:

| `data[0]` | Bedeutung |
|-----------|-----------|
| `0x00` | Erfolg — Authentifizierung akzeptiert |
| `0x02` | Unbekanntes Gerät — Device ID nicht registriert |
| andere | Fehler |

### Schritt 3: Post-Auth Parameter senden (CMD `0x6F`)

Nach erfolgreicher Authentifizierung müssen initiale Fahrzeugparameter gesetzt werden:

```
CMD: 0x6F
DATA: [fahrzeugspezifische Parameter]
```

### Vollständiger Ablauf

```
App                                Scooter
 │                                    │
 │─── CMD 0x30 [keyIdx, devId] ─────→│
 │                                    │
 │←─── CMD 0x30 [0x00 = OK] ─────────│
 │                                    │
 │─── CMD 0x6F [Post-Auth] ─────────→│
 │                                    │
 │←─── Telemetrie (0x90, 0x92) ──────│  (ab jetzt kontinuierlich)
 │                                    │
```

---

## Challenge-Response Authentifizierung

Die vollständige Challenge-Response Auth (CMD `0x31`) ist in der Firmware implementiert, wird aber aktuell auf PID 23452 **nicht erzwungen**. Der Ablauf wäre:

1. App sendet Auth Request (CMD `0x30`)
2. Scooter antwortet mit Challenge-Daten
3. App verschlüsselt Challenge mit AES-128-ECB
4. App sendet verschlüsselten Response (CMD `0x31`)
5. Scooter verifiziert und gewährt Zugang

Da die einfache Auth für den DE-Markt ausreicht, wird die Challenge-Response Auth hier nur der Vollständigkeit halber erwähnt.

---

## Device ID

Die Device ID ist eine 6 Byte lange Kennung, die den Nutzer identifiziert. Sie entspricht der **Navee-Account-ID** des Benutzers und wird bei der Ersteinrichtung über die offizielle Navee-App mit dem Scooter gepaart.

### Quellen für die Device ID

1. **BT-HCI-Capture** — Aus dem Bluetooth-Mitschnitt der offiziellen App extrahierbar (siehe unten)
2. **Offizielle App-Daten** — In den App-Daten / SharedPreferences der Navee-App gespeichert
3. **Navee-Server-API** — Über die Server-API abrufbar (erfordert Login)

---

## Device ID aus BT-Capture extrahieren

### Voraussetzung

- Android-Gerät mit aktiviertem BT-HCI-Logging
- Wireshark oder ähnliches Analyse-Tool

### Anleitung

1. **BT-HCI-Logging aktivieren:**
   - Entwickleroptionen → "Bluetooth-HCI-Snoop-Protokoll aktivieren"
   - Bluetooth aus-/einschalten

2. **Offizielle Navee-App verwenden:**
   - App starten und mit dem Scooter verbinden
   - Warten bis die App authentifiziert ist

3. **HCI-Log exportieren:**
   - `adb bugreport bugreport.zip`
   - HCI-Snoop-Datei aus dem Bugreport extrahieren

4. **In Wireshark analysieren:**
   - Filter: `btatt.handle == 0x0012` (Write-Handle der Navee-Characteristic)
   - Nach Paketen mit CMD `0x30` suchen
   - Die Bytes 3-8 im DATA-Feld sind die Device ID

### Beispiel

```
Frame im HCI-Capture:
55 AA 06 30 09 00 00 [D1 D2 D3 D4 D5 D6] 00 XX FE FD
                          └──────────────┘
                          Device ID (6 Bytes)
```

---

## Siehe auch

- [PROTOCOL.md](PROTOCOL.md) — Vollständige Protokoll-Referenz
- [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) — Reverse-Engineering Ergebnisse
