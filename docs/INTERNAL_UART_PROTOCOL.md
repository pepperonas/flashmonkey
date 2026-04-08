[English](INTERNAL_UART_PROTOCOL.md) | [Deutsch](INTERNAL_UART_PROTOCOL_DE.md)

# Internal UART Protocol — Dashboard ↔ Controller

Documentation of the internal UART communication protocol between the Navee ST3 Pro dashboard (RTL8762C) and the motor controller.

---

## Physical Layer

### 5-Wire Dashboard Cable Pinout

| Color  | Function              | Voltage  | Notes                                         |
|--------|-----------------------|----------|-----------------------------------------------|
| Black  | GND                   | 0V       | Reference ground                              |
| Red    | VCC (Battery)         | 53.04V   | WARNING: Do NOT connect to microcontroller    |
| Blue   | VCC (Dashboard)       | 52.2V    | WARNING: Do NOT connect to microcontroller    |
| Yellow | Controller RX         | 3.8V     | Dashboard → Controller data input (confirmed) |
| Green  | Controller TX         | ~4.12V   | Controller → Dashboard data output            |

### UART Parameters

| Parameter   | Value       |
|-------------|-------------|
| Baud Rate   | 19200       |
| Data Bits   | 8           |
| Parity      | None        |
| Stop Bits   | 1           |
| Logic Level | ~4V (non-standard — not 3.3V or 5V) |

The logic level of approximately 4V means direct connection to a 3.3V microcontroller (Arduino, ESP32) requires a logic level shifter. In practice, 5V Arduino inputs have tolerated this signal directly in testing, but a level shifter is recommended for safe long-term use.

### Two-Wire Architecture (discovered 2026-04-08)

The UART is standard two-wire full-duplex, NOT single-wire half-duplex as originally assumed:

| Wire   | Function           | Direction              | Voltage | Notes |
|--------|--------------------|------------------------|---------|-------|
| Yellow | Controller RX      | Dashboard → Controller | 3.8V    | Dashboard sends commands to controller |
| Green  | Controller TX      | Controller → Dashboard | 4.12V   | Controller sends responses to dashboard |

**Evidence:**
1. **Disconnecting Yellow causes error beeping** — the controller expects data on Yellow and alarms when it stops
2. **CP2102 TX (3.3V) on Yellow kills all communication** — voltage mismatch (3.3V vs 3.8V) disrupts the controller, 0 bytes received on Green during test
3. **Yellow at 0V when disconnected from dashboard** — the dashboard drives Yellow at 3.8V
4. **Navee service technician video** shows USB-UART adapter connected to both Yellow AND Green wires
5. **RoboCoffee documentation** describes "standard two-wire UART (TX+RX)" for Brightway scooters

**Why Green shows both 0x61 and 0x64 frames:** Green is Controller TX (0x64 frames). The 0x61 frames visible on Green are the controller internally echoing/mirroring the received dashboard commands back on its TX line — a common pattern where the controller reflects its input state for debugging or protocol symmetry. This is NOT a shared bus.

**Implication:** All previous UART attempts (MitM, direct flash, hybrid) failed because we sent commands on Green — but the controller receives commands on Yellow. The controller never saw our data.

**Challenge:** The Yellow wire operates at 3.8V logic level. Standard CP2102 adapters output 3.3V, which is too low. A 3.3V→5V level shifter or a 5V-capable UART adapter is needed to properly drive the Yellow wire.

---

## Frame Format

The internal UART protocol uses a different frame structure than the BLE protocol. There is no `0x55 0xAA` header. Instead, it uses complementary header/footer byte pairs.

```
┌──────────┬──────────────┬──────────┬──────────┐
│ Header   │ DATA         │ Checksum │ Footer   │
│ 1 Byte   │ n Bytes      │ 1 Byte   │ 1 Byte   │
└──────────┴──────────────┴──────────┴──────────┘
```

### Header / Footer Complement Pairs

Header and Footer are always complements: `Header XOR Footer = 0xFF`.

| Direction              | Header | Footer | Complement Check        |
|------------------------|--------|--------|-------------------------|
| Dashboard → Controller | `0x61` | `0x9E` | `0x61 + 0x9E = 0xFF` ✅ |
| Controller → Dashboard | `0x64` | `0x9B` | `0x64 + 0x9B = 0xFF` ✅ |

### Checksum Calculation

```
Checksum = SUM(all bytes before checksum position) & 0xFF
```

This includes the header byte through the last data byte. Verified against all three frame types. ✅

---

## Frame Types

### Frame A — Dashboard Status (Dashboard → Controller)

**Length:** 15 bytes | **Frequency:** ~5 times per second | **Direction:** Dashboard → Controller

```
61 30 0A [MODE] [LIGHT] [B5] [SPD_A] [SPD_B] [B8] [B9] [STARTUP] [B11] [B12] [CHK] 9E
```

| Offset | Field          | Observed Values                    | Verified         |
|--------|----------------|------------------------------------|------------------|
| 0      | Header         | `0x61`                             | ✅               |
| 1      | Command        | `0x30`                             | ✅               |
| 2      | Data Length    | `0x0A` (10)                        | ✅               |
| 3      | Drive Mode     | `0x35` = ECO, `0x33` = SPORT       | ✅ Live verified  |
| 4      | Headlight      | `0x04` = ON, `0x00` = OFF          | ✅ Live verified  |
| 5      | Unknown        | `0x88` (136) — constant            | Possibly bitfield |
| 6      | Speed Value A  | `0x17` (23) typical                | Observed          |
| 7      | Speed Value B  | `0x16` (22) typical                | Observed          |
| 8      | Unknown        | `0x01` — constant                  |                   |
| 9      | Unknown        | `0x00` — mostly zero               |                   |
| 10     | Startup Speed  | `0x0A` (10 km/h) or `0x00`         | Identified        |
| 11–12  | Padding        | `0x00 0x00` — always zero          |                   |
| 13     | Checksum       | SUM(bytes 0–12) & 0xFF             | ✅               |
| 14     | Footer         | `0x9E`                             | ✅               |

#### Observed Frame Variants

```
ECO,   Light ON:  61 30 0A 35 04 88 17 15 01 00 00 00 00 89 9E
ECO,   Light OFF: 61 30 0A 35 00 88 17 15 01 00 00 00 00 85 9E
SPORT, Light ON:  61 30 0A 33 04 88 17 15 01 00 00 00 00 87 9E
```

#### Speed Bytes 6 and 7 — Important Finding

These bytes were initially identified as speed limit control values sent from dashboard to controller. Arduino MitM testing (1000+ frames modified from `0x17`/`0x16` to `0x1E`/`0x1E`, i.e., 30/30 km/h) demonstrated that the controller completely ignores these values. The scooter remained at 22 km/h throughout testing.

**Conclusion:** Bytes 6 and 7 are telemetry or display values, not authoritative speed limit control. See the Speed Limit Architecture section below.

#### Startup Speed — Byte 10

- `0x0A` (10): Rolling start assist speed of 10 km/h
- `0x00` (0): No startup assist

---

### Frame B — Dashboard Telemetry (Dashboard → Controller)

**Length:** 14 bytes | **Frequency:** ~3 times per second | **Direction:** Dashboard → Controller

```
61 31 09 9A 64 CD 80 80 [VAR] 19 00 00 [CHK] 9E
```

| Offset | Field       | Observed Values             | Notes                                    |
|--------|-------------|-----------------------------|--------------------------------------------|
| 0      | Header      | `0x61`                      |                                            |
| 1      | Command     | `0x31`                      |                                            |
| 2      | Data Length | `0x09` (9)                  |                                            |
| 3–7    | Static      | `9A 64 CD 80 80`            | Constant across all observed frames        |
| 8      | Variable    | `0x00`–`0x04`               | Changes during operation — see note below |
| 9      | Static      | `0x19` (25)                 | Possibly temperature in °C (25°C ambient) |
| 10–11  | Padding     | `0x00 0x00`                 | Always zero                                |
| 12     | Checksum    | SUM(bytes 0–11) & 0xFF      |                                            |
| 13     | Footer      | `0x9E`                      |                                            |

#### Variable Byte 8

Byte 8 was observed to drop to `0x00`/`0x01` when the headlight was switched off (previously `0x02`–`0x04` with light on). Likely candidates: power consumption level, PWM duty cycle, or hall sensor feedback from the motor.

---

### Frame C — Controller Telemetry (Controller → Dashboard)

**Length:** 18 bytes | **Frequency:** ~1 time per second | **Direction:** Controller → Dashboard

```
64 26 0D 00 00 04 FB 04 FB 00 30 00 22 D5 48 64 68 9B
```

| Offset | Field       | Hex     | Decimal | Notes                                          |
|--------|-------------|---------|---------|------------------------------------------------|
| 0      | Header      | `0x64`  | —       | Controller frame                               |
| 1      | Command     | `0x26`  | —       |                                                |
| 2      | Data Length | `0x0D`  | 13      |                                                |
| 3–4    | Unknown     | `00 00` | 0, 0    | Possibly current speed (0 = stationary)        |
| 5–6    | Unknown     | `04 FB` | 1275    | Possibly battery voltage (1275 ÷ 25 ≈ 51V)    |
| 7–8    | Unknown     | `04 FB` | 1275    | Repeated voltage value or second measurement   |
| 9      | Unknown     | `0x00`  | 0       | Status flags?                                  |
| 10     | Unknown     | `0x30`  | 48      | Speed indicator (62 = stationary, 65+ = moving); 48 ÷ 2 = 24? |
| 11     | Unknown     | `0x00`  | 0       |                                                |
| 12     | Unknown     | `0x22`  | 34      | Possibly speed limit (0x22 hex = 22 decimal = 22 km/h?) |
| 13–14  | Unknown     | `D5 48` | —       | Possibly odometer or hash                      |
| 15     | Unknown     | `0x64`  | 100     | Battery percentage (100% = full) ✅            |
| 16     | Checksum    | `0x68`  | —       | SUM(bytes 0–15) & 0xFF ✅                      |
| 17     | Footer      | `0x9B`  | —       |                                                |

Frame C was observed to remain completely unchanged across mode switches (ECO ↔ SPORT) and headlight toggles. Values in Frame C are likely only updated during active riding.

---

### Special Frame — Mode Change Acknowledgement (Controller → Dashboard)

Observed once during a drive mode change. CMD `0x23`, 12 bytes total.

```
64 23 07 31 30 30 34 19 0A 18 8E 9B
```

| Offset | Hex           | ASCII  | Notes                                      |
|--------|---------------|--------|--------------------------------------------|
| 0      | `0x64`        | —      | Controller header                          |
| 1      | `0x23`        | —      | Command — mode acknowledgement             |
| 2      | `0x07`        | —      | Data length (7)                            |
| 3–6    | `31 30 30 34` | "1004" | Firmware version string or parameter set   |
| 7      | `0x19`        | —      | 25 decimal — possibly temperature in °C    |
| 8–9    | `0x0A 0x18`   | —      | Unknown                                    |
| 10     | `0x8E`        | —      | Checksum                                   |
| 11     | `0x9B`        | —      | Footer                                     |

This frame was only seen once and may be sent by the controller to confirm receipt of a mode change command from Frame A.

---

## Key Finding: Speed Limit Architecture

The UART MitM experiment (Arduino UNO inserted on the green wire) conclusively proved that the speed limit is not modifiable via UART frame manipulation.

### Test Setup

- Arduino Nano inserted between dashboard connector (green wire) and controller
- Frame A bytes 6 and 7 intercepted and rewritten from `0x17`/`0x16` to `0x1E`/`0x1E` (30/30 km/h)
- Checksum recalculated correctly for each modified frame
- Over 1168 frames successfully intercepted, modified, and forwarded
- Serial interface provided live control: `u` = unlock, `p` = passthrough, `+`/`-` for speed adjustment

### Result

The scooter remained at 22 km/h throughout the test. The controller did not respond to the modified values.

### Conclusion

```
Speed Limit Chain (normal operation):
  Dashboard FW (RTL8762C)
    → computes speed limit based on PID / region code
    → sends UART frames to controller
    → controller enforces limit from its own internal state

MitM Attack (tested):
  Dashboard → [Arduino modifies Frame A bytes 6-7] → Controller
    → Controller IGNORES the manipulated speed values
    → Speed remains at 22 km/h
```

The speed limit is enforced inside the controller firmware, not by the UART data stream. The dashboard UART frames reflect the configured limit as telemetry, but the controller does not use those values as its authoritative source. The limit must be addressed at the firmware level (RTL8762C patch at offset `0xF848`).

**Important update (2026-04-08):** The MitM test was conducted on the Green wire only. Since we now know the controller receives commands on the **Yellow wire**, the MitM result may be invalid — the controller may have been reading the unmodified frames from the dashboard on Yellow while we were modifying frames on Green. A proper MitM test would need to intercept the Yellow wire (Dashboard TX → Controller RX) with a level-shifted signal.

---

## Identified Bytes Summary

### Frame A — Confirmed Fields

| Offset | Function       | ECO + Light ON | SPORT + Light ON | ECO + Light OFF | Change Trigger |
|--------|----------------|----------------|------------------|-----------------|----------------|
| 3      | Drive Mode     | `0x35`         | `0x33`           | `0x35`          | Mode button    |
| 4      | Headlight      | `0x04`         | `0x04`           | `0x00`          | Light button   |
| 10     | Startup Speed  | `0x0A`         | —                | `0x00`          | Unknown        |

### Frame C — Candidate Fields (not fully verified)

| Offset | Value         | Hypothesis                              |
|--------|---------------|-----------------------------------------|
| 10     | `0x30` (48)   | Speed indicator (48 ÷ 2 = 24?) or raw counter |
| 12     | `0x22` (34)   | Speed limit in km/h (0x22 decimal = 34, but hex digits "22" = 22 km/h) |
| 15     | `0x64` (100)  | Battery percentage — confirmed at full charge |

---

## Required Hardware

| Device                                     | Purpose                                          |
|--------------------------------------------|--------------------------------------------------|
| USB-UART adapter (CP2102, FT232RL, CH340)  | UART debugging and protocol capture              |
| Multimeter                                 | Voltage measurement on signal lines              |
| Fine probe leads / Dupont cables           | Precise connections to signal lines              |
| Arduino Nano or ESP32 DevKit               | MitM controller for frame interception           |
| Logic level shifter (3.3V ↔ 5V)           | Required if microcontroller is not 5V-tolerant   |
| Solder wire (0.5–0.8mm)                    | Permanent installations                          |
| Heat shrink tubing                         | Insulation for solder joints                     |

---

## Open Questions

The following fields have not been definitively identified and warrant further investigation:

- Byte 5 in Frame A (`0x88`) — constant value, possibly a bitfield for additional flags
- Variable byte 8 in Frame B — confirm whether it correlates with throttle position or power draw
- Bytes 3–4 in Frame C — confirm whether they encode current speed during riding
- Bytes 5–8 in Frame C — confirm battery voltage hypothesis by measuring at various charge levels
- Byte 10 in Frame C — observe during riding to determine if it tracks speed
- Bytes 13–14 in Frame C (`D5 48`) — check for changes after riding distance; may be odometer

### Resolved Questions (2026-04-08)

- **Yellow wire function: CONFIRMED as Controller RX** (Dashboard → Controller data input at 3.8V logic level). Evidence: disconnecting Yellow causes error beeping; CP2102 3.3V TX on Yellow disrupts all communication; Navee service video shows both Yellow and Green connected to UART adapter.
- **UART topology: Standard two-wire full-duplex.** Yellow = Controller RX (Dashboard → Controller), Green = Controller TX (Controller → Dashboard). The 0x61 frames visible on Green are controller-internal echo/mirroring, not a shared bus. The controller receives commands exclusively on Yellow.
- **MitM test validity: QUESTIONABLE.** The Arduino MitM intercepted frames on Green only. The controller may have been reading unmodified dashboard frames on Yellow the entire time, rendering the MitM test inconclusive for speed limit modification via UART.

---

*Reference implementation: `/reverse-engineering/navee_uart_mitm_nano/`*

*© 2026 Martin Pfeffer*
