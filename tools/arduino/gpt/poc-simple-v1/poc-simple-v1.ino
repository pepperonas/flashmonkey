#include <SoftwareSerial.h>

SoftwareSerial ctrlSerial(2, 3); // RX=2 (optional), TX=3 (wichtig)

#define BAUD 19200

unsigned long lastSend = 0;

// 🔥 Speed Unlock Frame (40 km/h, Sport Mode)
uint8_t frame[] = {
  0x61, 0x30, 0x0A,
  0x33,       // Mode: SPORT
  0x00,
  0x88,
  0x28, 0x28, // Speed = 40
  0x01,
  0x00, 0x00, 0x00, 0x00,
  0x00,       // Checksum (wird berechnet)
  0x9E
};

// Checksum berechnen
uint8_t calcChecksum(uint8_t* f, int len) {
  uint8_t sum = 0;
  for (int i = 0; i < len - 2; i++) {
    sum += f[i];
  }
  return sum & 0xFF;
}

void setup() {
  Serial.begin(115200);
  ctrlSerial.begin(BAUD);

  Serial.println(">>> SIMPLE SEND TEST START <<<");

  // Checksum einmal berechnen
  frame[13] = calcChecksum(frame, sizeof(frame));
}

void loop() {
  unsigned long now = millis();

  // alle 200ms senden (~5Hz)
  if (now - lastSend >= 200) {
    lastSend = now;

    for (int i = 0; i < sizeof(frame); i++) {
      ctrlSerial.write(frame[i]);
    }

    Serial.println("Sent frame");
  }

  // optional: Controller antworten anzeigen
  while (ctrlSerial.available()) {
    uint8_t b = ctrlSerial.read();
    Serial.print(b, HEX);
    Serial.print(" ");
  }
}