/*
 * ============================================================
 * NAVEE ST3 Pro — UART MitM v2 (Yellow Wire / Correct Wiring)
 * ============================================================
 *
 * Board: Arduino Nano (ATmega328P, 5V)
 * Author: Martin Pfeffer
 * Version: 2.0
 *
 * WICHTIG: v1 hat die GRÜNE Ader abgefangen — das war FALSCH!
 * Grün = Controller TX (Ausgang). Der Controller empfängt auf GELB.
 * Daher hat der MitM v1 nie funktioniert: der Controller hat die
 * manipulierten Frames auf Grün nie gelesen.
 *
 * Verkabelung v2:
 * ===============
 *
 *   GELBE ADER DURCHTRENNEN! Dann:
 *
 *   Dashboard-Seite Gelb (Richtung Lenker)
 *       └──→ Nano Pin D2 (SoftSerial RX — empfängt vom Dashboard)
 *
 *   Nano Pin D3 (SoftSerial TX)
 *       └──[1kΩ]──→ Controller-Seite Gelb (Richtung Motor/Deck)
 *
 *   GRÜNE ADER bleibt VERBUNDEN (Controller TX → Dashboard RX)
 *   Optional: Grün ──→ Nano Pin D4 (SoftSerial2 RX — Monitor)
 *
 *   Scooter SCHWARZ (GND) ──→ Nano GND
 *   Nano USB ──→ Mac (Strom + Debug)
 *
 * Spannungen:
 * ===========
 *   Gelb: 3.8V idle (Dashboard treibt)
 *   Arduino 5V TX → 1kΩ Serienwiderstand → Controller Gelb (3.8V)
 *     Der 1kΩ begrenzt den Strom, Controller-RX Pull-up regelt Pegel
 *   Arduino 5V RX: 3.8V ist über HIGH-Schwelle (~2.5V) → OK
 *   Falls 1kΩ nicht reicht: Spannungsteiler 4.7kΩ + 15kΩ für exakt 3.8V
 *
 *   NIEMALS Rot oder Blau (53V!) an den Nano!
 *
 * Serial Monitor: 115200 Baud
 *   'p' = Passthrough (nur mithören — STANDARD)
 *   'u' = UNLOCK (Speed manipulieren)
 *   'l' = LOCK (Original-Speed)
 *   's' = Status
 *   '+' = Speed +1
 *   '-' = Speed -1
 *   'm' = Mode toggle (ECO 0x35 / SPORT 0x33)
 *   'd' = Debug (nächste 10 Frames raw ausgeben)
 *
 * Unterschied zu v1:
 *   - Gelb statt Grün abgefangen
 *   - Grün bleibt verbunden (Controller TX unberührt)
 *   - Optional: Grün auf D4 mitlesen (Controller-Antworten)
 *   - Mode-Override hinzugefügt
 *   - Debug-Modus für raw Frame-Dump
 *
 * © 2026 Martin Pfeffer
 */

#include <SoftwareSerial.h>

// ============================================================
// PINS — GELBE ADER (Dashboard TX → Controller RX)
// ============================================================
#define PIN_RX_FROM_DASHBOARD  2   // Empfängt Dashboard-Frames (Gelb, Lenker-Seite)
#define PIN_TX_TO_CONTROLLER   3   // Sendet an Controller (Gelb, Motor-Seite)

// Optional: Grüne Ader mitlesen (Controller TX → Dashboard RX)
#define PIN_RX_FROM_CONTROLLER 4   // Monitor Controller-Antworten (Grün)
#define MONITOR_GREEN          true // auf false setzen wenn D4 nicht verbunden

// ============================================================
// SERIAL
// ============================================================
SoftwareSerial yellowSerial(PIN_RX_FROM_DASHBOARD, PIN_TX_TO_CONTROLLER);

#if MONITOR_GREEN
SoftwareSerial greenSerial(PIN_RX_FROM_CONTROLLER, 5); // D5 = dummy TX (unused)
#endif

#define DEBUG_BAUD    115200
#define SCOOTER_BAUD  19200

// ============================================================
// PROTOKOLL
// ============================================================
#define HEADER_DASH   0x61
#define HEADER_CTRL   0x64
#define FOOTER_DASH   0x9E
#define FOOTER_CTRL   0x9B
#define CMD_STATUS    0x30   // Frame A (Dashboard → Controller)
#define CMD_TELEM     0x31   // Frame B (Dashboard → Controller)
#define CMD_CTRL_TEL  0x26   // Frame C (Controller → Dashboard)
#define FRAME_A_LEN   15
#define FRAME_B_LEN   14
#define FRAME_C_LEN   18
#define MAX_FRAME     32

// Frame A Byte-Positionen
#define B_MODE     3   // 0x35=ECO, 0x33=SPORT
#define B_LIGHT    4   // 0x04=AN, 0x00=AUS
#define B_BYTE5    5   // 0x88 (konstant)
#define B_SPEED_A  6   // Speed Value A
#define B_SPEED_B  7   // Speed Value B

// ============================================================
// SPEED CONFIG
// ============================================================
uint8_t targetA = 0x28;   // Ziel: 40 km/h
uint8_t targetB = 0x28;   // Ziel: 40 km/h
bool unlocked = false;
bool passthrough = true;   // Start im sicheren Modus
bool overrideMode = false;
uint8_t forceMode = 0x33;  // SPORT

// ============================================================
// FRAME PARSER (Yellow — Dashboard → Controller)
// ============================================================
uint8_t buf[MAX_FRAME];
uint8_t idx = 0;
bool inFrame = false;
uint8_t expectLen = 0;

// ============================================================
// STATS
// ============================================================
unsigned long cntA = 0, cntB = 0, cntC = 0, cntMod = 0;
unsigned long cntFwd = 0;
unsigned long lastLog = 0;
uint8_t debugCount = 0;   // Frames raw dumpen
bool firstFrame = true;

// Letzte Controller-Werte (von Grün)
uint8_t lastCtrlB10 = 0;
uint8_t lastCtrlB12 = 0;
uint8_t lastCtrlBat = 0;

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(DEBUG_BAUD);
  yellowSerial.begin(SCOOTER_BAUD);

  Serial.println(F("===================================="));
  Serial.println(F(" NAVEE ST3 Pro UART MitM v2"));
  Serial.println(F(" YELLOW WIRE Edition (correct RX!)"));
  Serial.println(F("===================================="));
  Serial.println(F(" GELBE Ader durchtrennt:"));
  Serial.println(F("   Dashboard Gelb -> D2 (RX)"));
  Serial.println(F("   D3 (TX) -> Controller Gelb"));
  Serial.println(F("   Grün bleibt verbunden!"));
  Serial.println(F("------------------------------------"));
  Serial.println(F(" p=Passthrough u=Unlock l=Lock"));
  Serial.println(F(" s=Status  +=Faster  -=Slower"));
  Serial.println(F(" m=Mode    d=Debug"));
  Serial.println(F("===================================="));
  Serial.println(F("[OK] Passthrough aktiv"));
  Serial.println(F("[OK] Warte auf Dashboard-Frames...\n"));
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  // USB-Befehle
  if (Serial.available()) handleCmd(Serial.read());

  // Dashboard-Frames von Gelb lesen (HAUPTAUFGABE)
  yellowSerial.listen();
  while (yellowSerial.available()) {
    processByte(yellowSerial.read());
  }

  // Controller-Antworten von Grün mitlesen (optional)
#if MONITOR_GREEN
  greenSerial.listen();
  unsigned long greenStart = millis();
  while (greenSerial.available() && (millis() - greenStart < 5)) {
    uint8_t b = greenSerial.read();
    processGreenByte(b);
  }
  // Zurück zu Yellow als primärer Listener
  yellowSerial.listen();
#endif

  // Status alle 10s
  if (millis() - lastLog > 10000) {
    printStatus();
    lastLog = millis();
  }
}

// ============================================================
// YELLOW BYTE VERARBEITUNG (Dashboard → Controller)
// ============================================================
void processByte(uint8_t b) {
  if (!inFrame) {
    if (b == HEADER_DASH) {
      inFrame = true;
      idx = 0;
      buf[idx++] = b;
    } else {
      // Nicht-Frame-Bytes direkt weiterleiten
      yellowSerial.write(b);
      cntFwd++;
    }
    return;
  }

  buf[idx++] = b;

  // Frame-Länge nach CMD-Byte bestimmen
  if (idx == 2) {
    switch (b) {
      case CMD_STATUS:    expectLen = FRAME_A_LEN; break;
      case CMD_TELEM:     expectLen = FRAME_B_LEN; break;
      default:            expectLen = 0; break;
    }
    if (expectLen == 0) { forwardYellow(); return; }
  }

  // Overflow
  if (idx >= MAX_FRAME) { forwardYellow(); return; }

  // Frame komplett?
  if (expectLen > 0 && idx >= expectLen) {
    handleDashboardFrame();
  }
}

// ============================================================
// DASHBOARD FRAME HANDLER (auf Gelb empfangen)
// ============================================================
void handleDashboardFrame() {
  // Footer prüfen
  if (buf[idx - 1] != FOOTER_DASH) { forwardYellow(); return; }

  // Checksum prüfen
  uint8_t chkPos = idx - 2;
  uint8_t chkGot = buf[chkPos];
  uint8_t chkCalc = calcChecksum(buf, chkPos);

  if (chkGot != chkCalc) {
    Serial.print(F("[ERR] CHK: got=0x"));
    Serial.print(chkGot, HEX);
    Serial.print(F(" calc=0x"));
    Serial.println(chkCalc, HEX);
    forwardYellow();
    return;
  }

  if (firstFrame) {
    Serial.println(F("[OK] Erster gültiger Frame empfangen!"));
    Serial.println(F("[OK] Dashboard -> Arduino -> Controller Kette aktiv!"));
    firstFrame = false;
  }

  uint8_t cmd = buf[1];

  if (cmd == CMD_STATUS) {
    cntA++;

    // Debug-Dump
    if (debugCount > 0) {
      debugCount--;
      Serial.print(F("[DBG] "));
      for (uint8_t i = 0; i < idx; i++) {
        if (buf[i] < 0x10) Serial.print('0');
        Serial.print(buf[i], HEX);
        Serial.print(' ');
      }
      Serial.println();
    }

    // Log alle 50 Frames
    if (cntA % 50 == 1) {
      Serial.print(F("[A] "));
      Serial.print(buf[B_MODE] == 0x35 ? F("ECO") : F("SPT"));
      Serial.print(buf[B_LIGHT] == 0x04 ? F(" L:ON") : F(" L:--"));
      Serial.print(F(" SA:"));
      Serial.print(buf[B_SPEED_A]);
      Serial.print(F(" SB:"));
      Serial.print(buf[B_SPEED_B]);
      if (unlocked && !passthrough) {
        Serial.print(F(" -> "));
        Serial.print(targetA);
        Serial.print(F("/"));
        Serial.print(targetB);
        Serial.print(F(" MOD!"));
      }
      Serial.println();
    }

    // === SPEED + MODE MANIPULATION ===
    if (!passthrough && unlocked) {
      buf[B_SPEED_A] = targetA;
      buf[B_SPEED_B] = targetB;

      if (overrideMode) {
        buf[B_MODE] = forceMode;
      }

      // Checksum neu berechnen
      buf[chkPos] = calcChecksum(buf, chkPos);
      cntMod++;
    }

  } else if (cmd == CMD_TELEM) {
    cntB++;
  }

  forwardYellow();
}

// ============================================================
// GREEN BYTE VERARBEITUNG (Controller TX — nur Monitor)
// ============================================================
#if MONITOR_GREEN
uint8_t greenBuf[MAX_FRAME];
uint8_t greenIdx = 0;
bool greenInFrame = false;
uint8_t greenExpect = 0;

void processGreenByte(uint8_t b) {
  if (!greenInFrame) {
    if (b == HEADER_CTRL) {
      greenInFrame = true;
      greenIdx = 0;
      greenBuf[greenIdx++] = b;
    }
    return;
  }

  greenBuf[greenIdx++] = b;

  if (greenIdx == 2) {
    if (b == CMD_CTRL_TEL) {
      greenExpect = FRAME_C_LEN;
    } else {
      greenInFrame = false;
      greenIdx = 0;
      return;
    }
  }

  if (greenIdx >= MAX_FRAME) { greenInFrame = false; greenIdx = 0; return; }

  if (greenExpect > 0 && greenIdx >= greenExpect) {
    // Frame C komplett
    if (greenBuf[greenIdx - 1] == FOOTER_CTRL) {
      cntC++;
      lastCtrlB10 = greenBuf[10];
      lastCtrlB12 = greenBuf[12];
      lastCtrlBat = greenBuf[15];

      // Log alle 10 Frames
      if (cntC % 10 == 1) {
        Serial.print(F("[C] B10:"));
        Serial.print(lastCtrlB10);
        Serial.print(F(" B12:0x"));
        Serial.print(lastCtrlB12, HEX);
        Serial.print(F(" Bat:"));
        Serial.print(lastCtrlBat);
        Serial.println(F("%"));
      }
    }
    greenInFrame = false;
    greenIdx = 0;
    greenExpect = 0;
  }
}
#endif

// ============================================================
// CHECKSUM
// ============================================================
uint8_t calcChecksum(uint8_t* data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) sum += data[i];
  return sum;
}

// ============================================================
// FORWARD YELLOW (an Controller weiterleiten)
// ============================================================
void forwardYellow() {
  for (uint8_t i = 0; i < idx; i++) {
    yellowSerial.write(buf[i]);
  }
  cntFwd++;
  inFrame = false;
  idx = 0;
  expectLen = 0;
}

// ============================================================
// STATUS
// ============================================================
void printStatus() {
  if (cntA > 0) {
    Serial.print(F("[STAT] A:"));
    Serial.print(cntA);
    Serial.print(F(" B:"));
    Serial.print(cntB);
    Serial.print(F(" C:"));
    Serial.print(cntC);
    Serial.print(F(" MOD:"));
    Serial.print(cntMod);
    Serial.print(F(" FWD:"));
    Serial.print(cntFwd);
    Serial.print(unlocked ? F(" UNLOCKED") : F(" pass"));
    Serial.print(F(" tgt:"));
    Serial.print(targetA);
    Serial.print(F("/"));
    Serial.println(targetB);
  } else {
    Serial.println(F("[WARN] Keine Frames! Gelbe Ader verbunden?"));
    Serial.println(F("  Dashboard Gelb -> D2"));
    Serial.println(F("  D3 -> Controller Gelb"));
  }
}

// ============================================================
// USB BEFEHLE
// ============================================================
void handleCmd(char c) {
  switch (c) {
    case 'p':
      passthrough = true; unlocked = false;
      Serial.println(F("\n[MODE] PASSTHROUGH — keine Manipulation\n"));
      break;

    case 'u':
      passthrough = false; unlocked = true;
      Serial.print(F("\n[MODE] UNLOCKED! Speed A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.print(targetB);
      Serial.println(F(" km/h"));
      if (overrideMode) {
        Serial.print(F("  Mode override: 0x"));
        Serial.println(forceMode, HEX);
      }
      Serial.println();
      break;

    case 'l':
      passthrough = false; unlocked = false;
      Serial.println(F("\n[MODE] LOCKED — Original-Speed\n"));
      break;

    case 's':
      Serial.println(F("\n========= STATUS ========="));
      Serial.print(F("Modus:     "));
      Serial.println(passthrough ? F("PASSTHROUGH") : unlocked ? F("UNLOCKED") : F("LOCKED"));
      Serial.print(F("Speed:     A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      Serial.print(F("Mode-OVR:  "));
      Serial.println(overrideMode ? (forceMode == 0x33 ? F("SPORT") : F("ECO")) : F("OFF"));
      Serial.print(F("Frames:    A="));
      Serial.print(cntA);
      Serial.print(F(" B="));
      Serial.print(cntB);
      Serial.print(F(" C="));
      Serial.println(cntC);
      Serial.print(F("Modified:  "));
      Serial.println(cntMod);
      Serial.print(F("Forwarded: "));
      Serial.println(cntFwd);
#if MONITOR_GREEN
      Serial.print(F("Ctrl B10:  "));
      Serial.println(lastCtrlB10);
      Serial.print(F("Ctrl B12:  0x"));
      Serial.println(lastCtrlB12, HEX);
      Serial.print(F("Ctrl Bat:  "));
      Serial.print(lastCtrlBat);
      Serial.println(F("%"));
#endif
      Serial.println(F("==========================\n"));
      break;

    case '+':
      if (targetA < 50) { targetA++; targetB++; }
      Serial.print(F("[SPD] A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      break;

    case '-':
      if (targetA > 5) { targetA--; targetB--; }
      Serial.print(F("[SPD] A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      break;

    case 'm':
      if (!overrideMode) {
        overrideMode = true;
        forceMode = 0x33; // SPORT
        Serial.println(F("[MODE] Override: SPORT (0x33)"));
      } else if (forceMode == 0x33) {
        forceMode = 0x35; // ECO
        Serial.println(F("[MODE] Override: ECO (0x35)"));
      } else {
        overrideMode = false;
        Serial.println(F("[MODE] Override: OFF"));
      }
      break;

    case 'd':
      debugCount = 10;
      Serial.println(F("[DBG] Nächste 10 Frame-A raw dumps"));
      break;
  }
}
