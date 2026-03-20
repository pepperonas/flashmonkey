/*
 * ============================================================
 * NAVEE ST3 Pro — UART Man-in-the-Middle Speed Unlock
 * ============================================================
 * 
 * Board: Arduino Nano (ATmega328P)
 * Author: Martin Pfeffer
 * Version: 1.0
 * 
 * Verkabelung:
 * ============
 * 
 *   GRÜNE ADER DURCHTRENNEN! Dann:
 * 
 *   Dashboard-Seite (Richtung Lenker)
 *       └──→ Nano Pin D2 (SoftSerial RX — empfängt vom Dashboard)
 * 
 *   Nano Pin D3 (SoftSerial TX)
 *       └──→ Controller-Seite (Richtung Motor)
 * 
 *   Scooter SCHWARZ (GND) ──→ Nano GND
 * 
 *   Nano USB ──→ Mac (Strom + Debug)
 * 
 * ⚠️  NIEMALS Rot oder Blau (53V!) an den Nano!
 * ⚠️  Nur Grün (durchtrennt) und Schwarz (GND)!
 * 
 * Serial Monitor: 115200 Baud
 *   'p' = Passthrough (nur mithören — STANDARD)
 *   'u' = UNLOCK (Speed manipulieren)
 *   'l' = LOCK (Original-Speed)
 *   's' = Status
 *   '+' = Speed +1
 *   '-' = Speed -1
 * 
 * © 2026 Martin Pfeffer
 */

#include <SoftwareSerial.h>

// ============================================================
// PINS
// ============================================================
#define PIN_RX_FROM_DASHBOARD  2   // Empfängt von Dashboard (grüne Ader, Lenker-Seite)
#define PIN_TX_TO_CONTROLLER   3   // Sendet an Controller (grüne Ader, Motor-Seite)

// ============================================================
// SERIAL
// ============================================================
SoftwareSerial scooterSerial(PIN_RX_FROM_DASHBOARD, PIN_TX_TO_CONTROLLER);

#define DEBUG_BAUD    115200
#define SCOOTER_BAUD  19200

// ============================================================
// PROTOKOLL
// ============================================================
#define HEADER_DASH   0x61
#define HEADER_CTRL   0x64
#define CMD_STATUS    0x30   // Frame A
#define CMD_TELEM     0x31   // Frame B
#define CMD_CTRL_TEL  0x26   // Frame C
#define FRAME_A_LEN   15
#define FRAME_B_LEN   14
#define FRAME_C_LEN   18
#define MAX_FRAME     32

// Frame A Byte-Positionen
#define B_MODE     3   // 0x35=ECO, 0x33=SPORT
#define B_LIGHT    4   // 0x04=AN, 0x00=AUS
#define B_SPEED_A  6   // Original: 0x17 (23)
#define B_SPEED_B  7   // Original: 0x15 (21)

// ============================================================
// SPEED CONFIG
// ============================================================
uint8_t targetA = 0x1E;   // Ziel: 30
uint8_t targetB = 0x1E;   // Ziel: 30
bool unlocked = false;
bool passthrough = true;   // Start im sicheren Modus

// ============================================================
// FRAME PARSER
// ============================================================
uint8_t buf[MAX_FRAME];
uint8_t idx = 0;
bool inFrame = false;
uint8_t expectLen = 0;
uint8_t curHeader = 0;

// ============================================================
// STATS
// ============================================================
unsigned long cntA = 0, cntB = 0, cntC = 0, cntMod = 0;
unsigned long lastLog = 0;

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(DEBUG_BAUD);
  scooterSerial.begin(SCOOTER_BAUD);
  
  Serial.println(F("================================"));
  Serial.println(F(" NAVEE ST3 Pro UART MitM"));
  Serial.println(F(" Arduino Nano Edition"));
  Serial.println(F("================================"));
  Serial.println(F(" p=Passthrough u=Unlock l=Lock"));
  Serial.println(F(" s=Status  +=Faster  -=Slower"));
  Serial.println(F("================================"));
  Serial.println(F("[OK] Passthrough-Modus aktiv"));
  Serial.println(F("[OK] Warte auf UART-Daten...\n"));
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  // USB-Befehle
  if (Serial.available()) handleCmd(Serial.read());
  
  // UART vom Dashboard lesen
  while (scooterSerial.available()) {
    processByte(scooterSerial.read());
  }
  
  // Status alle 10s
  if (millis() - lastLog > 10000) {
    if (cntA > 0) {
      Serial.print(F("[STAT] A:"));
      Serial.print(cntA);
      Serial.print(F(" B:"));
      Serial.print(cntB);
      Serial.print(F(" C:"));
      Serial.print(cntC);
      Serial.print(F(" MOD:"));
      Serial.print(cntMod);
      Serial.println(unlocked ? F(" UNLOCKED") : F(" passthrough"));
    } else {
      Serial.println(F("[WARN] Keine Frames. UART verbunden?"));
    }
    lastLog = millis();
  }
}

// ============================================================
// BYTE VERARBEITUNG
// ============================================================
void processByte(uint8_t b) {
  if (!inFrame) {
    if (b == HEADER_DASH || b == HEADER_CTRL) {
      inFrame = true;
      idx = 0;
      curHeader = b;
      buf[idx++] = b;
    } else {
      scooterSerial.write(b);
    }
    return;
  }
  
  buf[idx++] = b;
  
  // Frame-Länge bestimmen nach CMD-Byte
  if (idx == 2) {
    switch (b) {
      case CMD_STATUS:    expectLen = FRAME_A_LEN; break;
      case CMD_TELEM:     expectLen = FRAME_B_LEN; break;
      case CMD_CTRL_TEL:  expectLen = FRAME_C_LEN; break;
      default:            expectLen = 0; break;
    }
    if (expectLen == 0) { forward(); return; }
  }
  
  // Overflow-Schutz
  if (idx >= MAX_FRAME) { forward(); return; }
  
  // Frame komplett?
  if (expectLen > 0 && idx >= expectLen) {
    handleFrame();
  }
}

// ============================================================
// FRAME HANDLER
// ============================================================
void handleFrame() {
  uint8_t footer = buf[idx - 1];
  uint8_t expectFooter = 0xFF - curHeader;
  
  // Footer prüfen
  if (footer != expectFooter) { forward(); return; }
  
  // Checksum prüfen
  uint8_t chkPos = idx - 2;
  uint8_t chkGot = buf[chkPos];
  uint8_t chkCalc = calcChecksum(buf, chkPos);
  
  if (chkGot != chkCalc) {
    Serial.print(F("[ERR] Bad CHK: "));
    Serial.print(chkGot, HEX);
    Serial.print(F("!="));
    Serial.println(chkCalc, HEX);
    forward();
    return;
  }
  
  uint8_t cmd = buf[1];
  
  if (cmd == CMD_STATUS) {
    cntA++;
    
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
        Serial.print(F(" ->"));
        Serial.print(targetA);
        Serial.print(F("/"));
        Serial.print(targetB);
      }
      Serial.println();
    }
    
    // SPEED MANIPULATION
    if (unlocked && !passthrough) {
      buf[B_SPEED_A] = targetA;
      buf[B_SPEED_B] = targetB;
      buf[chkPos] = calcChecksum(buf, chkPos);
      cntMod++;
    }
  } else if (cmd == CMD_CTRL_TEL) {
    cntC++;
    if (cntC % 50 == 1) {
      Serial.print(F("[C] B10:"));
      Serial.print(buf[10]);
      Serial.print(F(" B12:0x"));
      Serial.print(buf[12], HEX);
      Serial.print(F(" B15:"));
      Serial.print(buf[15]);
      Serial.println(F("%"));
    }
  } else if (cmd == CMD_TELEM) {
    cntB++;
  }
  
  forward();
}

// ============================================================
// CHECKSUM
// ============================================================
uint8_t calcChecksum(uint8_t* data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) sum += data[i];
  return sum;
}

// ============================================================
// FORWARD BUFFER
// ============================================================
void forward() {
  for (uint8_t i = 0; i < idx; i++) {
    scooterSerial.write(buf[i]);
  }
  inFrame = false;
  idx = 0;
  expectLen = 0;
}

// ============================================================
// USB BEFEHLE
// ============================================================
void handleCmd(char c) {
  switch (c) {
    case 'p':
      passthrough = true; unlocked = false;
      Serial.println(F("\n[MODE] PASSTHROUGH\n"));
      break;
    case 'u':
      passthrough = false; unlocked = true;
      Serial.print(F("\n[MODE] UNLOCKED! A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      Serial.println();
      break;
    case 'l':
      passthrough = false; unlocked = false;
      Serial.println(F("\n[MODE] LOCKED\n"));
      break;
    case 's':
      Serial.println(F("\n--- STATUS ---"));
      Serial.print(F("Mode: "));
      Serial.println(passthrough ? F("PASSTHROUGH") : unlocked ? F("UNLOCKED") : F("LOCKED"));
      Serial.print(F("Target: A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      Serial.print(F("Frames: A="));
      Serial.print(cntA);
      Serial.print(F(" B="));
      Serial.print(cntB);
      Serial.print(F(" C="));
      Serial.println(cntC);
      Serial.print(F("Modified: "));
      Serial.println(cntMod);
      Serial.println(F("--------------\n"));
      break;
    case '+':
      if (targetA < 50) { targetA++; targetB++; }
      Serial.print(F("[SPD] A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      break;
    case '-':
      if (targetA > 10) { targetA--; targetB--; }
      Serial.print(F("[SPD] A="));
      Serial.print(targetA);
      Serial.print(F(" B="));
      Serial.println(targetB);
      break;
  }
}
