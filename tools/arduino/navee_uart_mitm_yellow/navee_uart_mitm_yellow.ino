/*
 * ============================================================
 * NAVEE ST3 Pro — UART MitM v2.4 (Yellow Wire Protocol!)
 * ============================================================
 *
 * DURCHBRUCH: Die gelbe Ader nutzt ein ANDERES Protokoll!
 *   Grün:  61 30 0A ... 9E  (Header 0x61, Footer 0x9E)
 *   Gelb:  51 10 09 ... AE  (Header 0x51, Footer 0xAE)
 *
 * Yellow Frame (14 Bytes):
 *   51 10 09 [MODE] [LIGHT] [88] [?] [?] [1E] [?] [SPEED] [?] [CHK] AE
 *   Byte  3: Mode (0x35=ECO, 0x33=SPORT)
 *   Byte  4: Light (0x04=ON, 0x00=OFF)
 *   Byte  8: Unknown (0x1E = 30)
 *   Byte 10: SPEED LIMIT (0x16 = 22 km/h) ← DER SCHLÜSSEL!
 *
 * Verkabelung:
 *   GELBE ADER DURCHTRENNEN!
 *   Dashboard Gelb ──→ Arduino D2 (RX)
 *   Arduino D3 (TX) ──→ Controller Gelb
 *   Schwarz ──→ GND | USB ──→ Mac
 *
 * Serial Monitor: 115200 Baud
 *   u=Unlock p=Pass +=Fast -=Slow s=Status d=Debug
 *
 * © 2026 Martin Pfeffer
 */

#include <SoftwareSerial.h>

#define PIN_RX  2
#define PIN_TX  3

SoftwareSerial scooterSerial(PIN_RX, PIN_TX);

#define SCOOTER_BAUD 19200
#define DEBUG_BAUD   115200
#define BUF_SIZE     128
#define FLUSH_TIMEOUT_MS 12

// Yellow wire frame
#define Y_HEADER     0x51
#define Y_FOOTER     0xAE
#define Y_FRAME_LEN  14
#define Y_B_MODE     3    // 0x35=ECO, 0x33=SPORT
#define Y_B_LIGHT    4    // 0x04=ON, 0x00=OFF
#define Y_B_SPD1     8    // Unknown speed byte (0x1E = 30)
#define Y_B_SPEED   10    // SPEED LIMIT (0x16 = 22 km/h)
#define Y_B_CHK     12    // Checksum position

// Speed config
uint8_t targetSpeed = 25;   // km/h — vorsichtig anfangen!
bool unlocked = false;

// Buffer
uint8_t buf[BUF_SIZE];
uint8_t bufLen = 0;
unsigned long lastByteTime = 0;

// Stats
unsigned long cntFrame = 0;
unsigned long cntMod = 0;
unsigned long cntFlush = 0;
unsigned long lastLog = 0;
uint8_t debugDump = 0;

void setup() {
  Serial.begin(DEBUG_BAUD);
  scooterSerial.begin(SCOOTER_BAUD);

  Serial.println(F("=================================="));
  Serial.println(F(" NAVEE MitM v2.4 YELLOW PROTOCOL"));
  Serial.println(F(" Frame: 51 10 09 ... AE"));
  Serial.println(F(" Speed byte at offset 10"));
  Serial.println(F("=================================="));
  Serial.println(F(" u=Unlock p=Pass +=Fast -=Slow"));
  Serial.println(F("=================================="));
}

void loop() {
  if (Serial.available()) handleCmd(Serial.read());

  while (scooterSerial.available() && bufLen < BUF_SIZE) {
    buf[bufLen++] = scooterSerial.read();
    lastByteTime = millis();
  }

  if (bufLen > 0 && (bufLen >= BUF_SIZE || millis() - lastByteTime >= FLUSH_TIMEOUT_MS)) {
    processAndFlush();
  }

  if (millis() - lastLog > 10000) {
    lastLog = millis();
    Serial.print(F("[S] frames:"));
    Serial.print(cntFrame);
    Serial.print(F(" mod:"));
    Serial.print(cntMod);
    Serial.print(F(" flush:"));
    Serial.print(cntFlush);
    Serial.println(unlocked ? F(" UNLOCK") : F(" pass"));
  }
}

void processAndFlush() {
  // Scan for Yellow frames: 51 10 09 ... AE (14 bytes)
  for (uint8_t i = 0; i + Y_FRAME_LEN - 1 < bufLen; i++) {
    if (buf[i] != Y_HEADER) continue;
    if (buf[i + 1] != 0x10) continue;
    if (buf[i + 2] != 0x09) continue;
    if (buf[i + Y_FRAME_LEN - 1] != Y_FOOTER) continue;

    // Checksum verify
    uint8_t chk = 0;
    for (uint8_t j = i; j < i + Y_B_CHK; j++) chk += buf[j];
    if (chk != buf[i + Y_B_CHK]) continue;

    // Valid frame!
    cntFrame++;

    // Debug
    if (debugDump > 0) {
      debugDump--;
      Serial.print(F("[F] "));
      for (uint8_t j = i; j < i + Y_FRAME_LEN; j++) {
        if (buf[j] < 0x10) Serial.print('0');
        Serial.print(buf[j], HEX);
        Serial.print(' ');
      }
      Serial.print(F(" spd:"));
      Serial.println(buf[i + Y_B_SPEED]);
    }

    // Log
    if (cntFrame % 50 == 1) {
      Serial.print(F("[Y] "));
      Serial.print(buf[i + Y_B_MODE] == 0x35 ? F("ECO") : F("SPT"));
      Serial.print(buf[i + Y_B_LIGHT] == 0x04 ? F(" L:ON") : F(" L:--"));
      Serial.print(F(" spd:"));
      Serial.print(buf[i + Y_B_SPEED]);
      if (unlocked) {
        Serial.print(F(" ->"));
        Serial.print(targetSpeed);
      }
      Serial.println();
    }

    // === SPEED MODIFICATION ===
    if (unlocked) {
      // NUR Byte 10 ändern! Byte 8 (0x1E) nicht anfassen!
      buf[i + Y_B_SPEED] = targetSpeed;  // Byte 10 (was 0x16=22)
      // Recalculate checksum
      chk = 0;
      for (uint8_t j = i; j < i + Y_B_CHK; j++) chk += buf[j];
      buf[i + Y_B_CHK] = chk;
      cntMod++;
    }
  }

  scooterSerial.write(buf, bufLen);
  cntFlush++;
  bufLen = 0;
}

void handleCmd(char c) {
  switch (c) {
    case 'u':
      unlocked = true;
      Serial.print(F("[UNLOCK] speed:"));
      Serial.println(targetSpeed);
      break;
    case 'p':
      unlocked = false;
      Serial.println(F("[PASS]"));
      break;
    case '+':
      if (targetSpeed < 50) targetSpeed++;
      Serial.print(F("[SPD] "));
      Serial.println(targetSpeed);
      break;
    case '-':
      if (targetSpeed > 5) targetSpeed--;
      Serial.print(F("[SPD] "));
      Serial.println(targetSpeed);
      break;
    case 's':
      Serial.print(F("Mode:"));
      Serial.println(unlocked ? F("UNLOCK") : F("PASS"));
      Serial.print(F("Speed:"));
      Serial.println(targetSpeed);
      Serial.print(F("Frames:"));
      Serial.print(cntFrame);
      Serial.print(F(" Mod:"));
      Serial.println(cntMod);
      break;
    case 'd':
      debugDump = 10;
      Serial.println(F("[DBG] 10 dumps"));
      break;
  }
}
