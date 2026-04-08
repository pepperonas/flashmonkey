# Direct UART Flash — BLDC Controller

Flash the BLDC motor controller directly via UART, bypassing the dashboard entirely.
Based on the Navee service tool "Download_Tool_S" discovered in a YouTube service video.

## How It Works

The BLDC controller has its own UART bootloader. The Navee service tool connects a USB-UART adapter directly to the controller (dashboard disconnected) and sends firmware via XMODEM.

## Critical Discovery: Two-Wire UART (2026-04-08)

The UART is standard **two-wire full-duplex**, NOT single-wire half-duplex:

| Wire   | Function           | Direction              | Voltage | Role |
|--------|--------------------|------------------------|---------|------|
| **Yellow** | **Controller RX** | Dashboard → Controller | 3.8V    | Controller receives commands here |
| **Green**  | **Controller TX**  | Controller → Dashboard | 4.12V   | Controller sends responses here |

**This explains why all previous UART attempts failed:** We always sent on Green, but the controller only receives on Yellow!

### Evidence
1. Disconnecting Yellow from dashboard → **controller beeps** (error: no dashboard signal)
2. CP2102 TX (3.3V) on Yellow → **kills all communication** (voltage too low, controller confused)
3. 0x61 frames visible on Green are **controller-internal echo** (controller mirrors received commands on its TX line), not a shared bus
4. Navee service technician video shows adapter connected to **both** Yellow and Green
5. Different idle voltages: Green=4.12V, Yellow=3.8V (separate drivers)

### Voltage Level Problem
The Yellow wire operates at **3.8V logic level**. Standard CP2102 adapters output only 3.3V, which is insufficient. Solutions:
- Use a **3.3V→5V level shifter** between CP2102 TX and Yellow wire
- Use a **5V-capable UART adapter** (some CP2102 boards have a 3.3V/5V jumper)
- Use an **Arduino 5V** as UART bridge (Serial at 19200, pin-to-Yellow with voltage divider on RX)

## Hardware Setup

```
CP2102 USB-UART          Scooter Cable Harness
  TX  ─────────────────  Yellow wire (Controller RX)
  RX  ─────────────────  Green wire  (Controller TX)
  GND ─────────────────  Black wire  (GND)
  
  DO NOT CONNECT:
  - Red wire (53V battery!)
  - Blue wire (52V battery!)
```

**IMPORTANT:** The UART is standard two-wire full-duplex:
- **Yellow** = Controller RX (controller receives commands on this line)
- **Green** = Controller TX (controller sends responses on this line)

The dashboard stays connected for power, but disconnect the **Yellow wire** from the dashboard side so the CP2102 can send commands directly to the controller without interference.

This was confirmed by the Navee service technician setup (visible in service video) where both Yellow and Green wires are connected to the USB-UART adapter.

## Procedure

### Step 1: Prepare Wiring
Dashboard stays connected for power. Disconnect only the **Yellow wire** from the dashboard side. This lets the CP2102 send commands directly to the controller on Yellow without interference from the dashboard.

### Step 2: Connect CP2102 (with level shifter)
- CP2102 TX → **Level Shifter (3.3V→5V)** → Yellow wire (Controller RX)
- CP2102 RX → Green wire (Controller TX)
- CP2102 GND → Black wire
- Connect CP2102 to Mac via USB

**Without level shifter (fallback):** If your CP2102 has a 5V jumper, set it to 5V and connect TX directly to Yellow. The 5V output is closer to the 3.8V bus level and may be tolerated by the controller's input.

### Step 3: Power On Scooter
Turn on the scooter (battery must be connected). The controller powers up and, without a dashboard responding, should enter its UART bootloader.

### Step 4: Detect Controller
```bash
python3 tools/uart_direct_flasher.py --detect
```
This listens for 30 seconds. Expected: the controller sends 'C' (0x43) repeatedly, requesting XMODEM CRC mode.

### Step 5: Flash Firmware

**Safe test (same firmware that's already installed):**
```bash
python3 tools/uart_direct_flasher.py \
    tools/firmware/navee_bldc_v0.0.1.5_ST3_PRO_DE_22km_h,_pid=23452.bin
```

**Speed unlock (Global firmware):**
```bash
python3 tools/uart_direct_flasher.py \
    tools/firmware/navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin
```

### Step 6: Reconnect Dashboard
Resolder/reconnect the dashboard to the cable harness. Power cycle the scooter.

## Protocol Details

Based on "Download_Tool_S" screenshots:

| Parameter | Value |
|-----------|-------|
| Baud Rate | 19200 (possibly 115200) |
| Data Bits | 8 |
| Parity | None |
| Stop Bits | 1 |
| Protocol | XMODEM-CRC (128-byte blocks) |
| Block Format | SOH + seq + ~seq + 128 data + CRC-16 BE |
| File | Complete .bin including 16-byte Navee header |

### XMODEM Flow
1. Controller sends `'C'` (0x43) when ready for CRC mode
2. Tool sends blocks: `[01] [seq] [~seq] [128 bytes] [CRC-HI] [CRC-LO]`
3. Controller responds: ACK (0x06) or NAK (0x15) per block
4. After last block: EOT (0x04)
5. Controller confirms completion

### Block Count Verification
| Firmware Size | Blocks | Models |
|--------------|--------|--------|
| 41,088 bytes | 321 | S40, S60, V50i Pro, V25/V25i |
| 43,136 bytes | 337 | N65i |
| 45,184 bytes | 353 | E20, E25, V40i Pro II |
| 47,232 bytes | 369 | ST3, GT3, G5, V3 Pro |
| 49,280 bytes | 385 | UT3 Max |
| 53,376 bytes | 417 | ST3 PRO DE, GT5 Max |

The service tool showed "Total Data Blocks: 321" for an S40 firmware (41,088 bytes / 128 = 321). Confirms complete file is sent including header.

## 2-Wire UART Notes

The UART uses two separate wires (full-duplex):
- **Green** = Controller TX → CP2102 RX (reading)
- **Yellow** = Controller RX ← CP2102 TX (sending)

No echo handling needed — TX and RX are on separate lines. This was previously assumed to be half-duplex (single wire), which caused all UART flash attempts to fail because we sent on Green (Controller TX) instead of Yellow (Controller RX). The 0x61 frames visible on Green are controller-internal echo, not a shared bus.

## Baudrate

Try 19200 first (normal UART speed). If no response, try:
```bash
python3 tools/uart_direct_flasher.py --detect --baud 115200
python3 tools/uart_direct_flasher.py --detect --baud 57600
python3 tools/uart_direct_flasher.py --detect --baud 9600
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No 'C' signal | TX on wrong wire | TX must go to **Yellow** (Controller RX), not Green |
| No 'C' signal | Voltage too low | CP2102 3.3V is insufficient for 3.8V bus — use level shifter |
| No 'C' signal | Wrong baud rate | Try 115200 |
| No 'C' signal | Controller not powered | Check battery, turn on scooter |
| 0 bytes received | CP2102 TX on Yellow disrupting bus | Check level shifter, ensure 3.8V+ output |
| Controller beeping | Yellow wire disconnected | Dashboard Yellow must stay connected OR be properly driven |
| NAK on blocks | Wrong baud or CRC | Check baud, try checksum mode |
| 0x61 frames on Green | Normal — controller echo | Controller mirrors received commands on its TX line |
