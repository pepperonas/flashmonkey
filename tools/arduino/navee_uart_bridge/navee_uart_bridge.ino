/*
 * ============================================================
 * NAVEE ST3 Pro — UART Bridge (Mac → Yellow → Controller)
 * ============================================================
 *
 * Der Arduino ist eine Brücke zwischen Mac und Controller:
 *   Mac USB (3.3V) → Arduino HW Serial → SoftSerial → Yellow (5V) → Controller
 *   Controller → Green (4.1V) → SoftSerial → Arduino HW Serial → Mac USB
 *
 * Der Arduino löst das Spannungsproblem:
 *   CP2102 3.3V TX war zu niedrig für den 3.8V Yellow-Bus
 *   Arduino 5V TX funktioniert!
 *
 * Verkabelung:
 * ============
 *   Arduino D3 (SoftSerial TX) ──→ Controller Gelb (Controller RX)
 *   Arduino D2 (SoftSerial RX) ──→ Grün (Controller TX, Antworten lesen)
 *   Scooter Schwarz (GND)      ──→ Arduino GND
 *   Arduino USB                ──→ Mac
 *
 *   Dashboard Gelb: GETRENNT vom Controller (Dashboard-Seite offen)
 *   Grüne Ader: bleibt am Dashboard UND geht zusätzlich an D2
 *
 * Auf dem Mac:
 *   python3 tools/uart_direct_flasher.py --port /dev/tty.usbmodem* --detect
 *   python3 tools/uart_direct_flasher.py --port /dev/tty.usbmodem* firmware.bin
 *
 * Der Bridge-Sketch leitet alles 1:1 durch:
 *   USB RX → SoftSerial TX (Mac → Controller, über Gelb)
 *   SoftSerial RX → USB TX (Controller → Mac, über Grün)
 *
 * © 2026 Martin Pfeffer
 */

#include <SoftwareSerial.h>

#define PIN_RX_GREEN  2   // Controller TX (Grün) → lesen
#define PIN_TX_YELLOW 3   // → Controller RX (Gelb) → senden

SoftwareSerial controllerSerial(PIN_RX_GREEN, PIN_TX_YELLOW);

#define SCOOTER_BAUD 19200

void setup() {
  Serial.begin(SCOOTER_BAUD);          // USB ↔ Mac (gleiche Baudrate!)
  controllerSerial.begin(SCOOTER_BAUD); // ↔ Controller

  // LED kurz blinken = bereit
  pinMode(13, OUTPUT);
  digitalWrite(13, HIGH);
  delay(200);
  digitalWrite(13, LOW);
}

void loop() {
  // Mac → Controller (über Gelb)
  while (Serial.available()) {
    uint8_t b = Serial.read();
    controllerSerial.write(b);
  }

  // Controller → Mac (über Grün)
  while (controllerSerial.available()) {
    uint8_t b = controllerSerial.read();
    Serial.write(b);
  }
}
