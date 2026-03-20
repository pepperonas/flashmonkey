# Hardware — Navee ST3 Pro

[English](HARDWARE.md) | [Deutsch](HARDWARE_DE.md)

Complete hardware reference for the Navee ST3 Pro e-scooter dashboard unit, internal wiring, motor controller interface, and debug access.

---

## Table of Contents

- [Overview](#overview)
- [Dashboard (Meter Unit)](#dashboard-meter-unit)
- [Internal Wiring — Dashboard to Controller Cable](#internal-wiring--dashboard-to-controller-cable)
- [Motor Controller](#motor-controller)
- [Battery](#battery)
- [Speed Limiter Cable — Older Revisions](#speed-limiter-cable--older-revisions)
- [RTL8762C Download Mode](#rtl8762c-download-mode)
- [Flash Memory Layout](#flash-memory-layout)
- [BLE Radio](#ble-radio)
- [Photos](#photos)

---

## Overview

| Property | Value |
|----------|-------|
| Model | Navee ST3 Pro |
| PID (DE market) | 23452 — 22 km/h firmware limit |
| PID (Global) | 23451 — 30 km/h firmware limit |
| Market | Germany / EU regulated |
| Dashboard MCU | Realtek RTL8762C BLE SoC |
| UART baud rate | 19200 (normal operation) |

The ST3 Pro uses a single-chip design in the dashboard: the Realtek RTL8762C handles both BLE communication with the companion app and all dashboard logic (speed display, mode selection, light control). There is no separate BLE module — radio and application firmware run on the same MCU.

---

## Dashboard (Meter Unit)

The dashboard is the primary control interface and the unit that communicates wirelessly with the Android/iOS app.

| Property | Value |
|----------|-------|
| MCU | Realtek RTL8762C BLE SoC |
| CPU core | ARM Cortex-M4F, 40 MHz |
| Module | RB8762-35A1 (Navee custom module) |
| Serial number | 251210A5629ABB3E |
| MAC address | 10:A5:62:9A:BB:3E (read via `rtltool read_mac`) |
| FCC ID | 2A4GZ-RB87623SAI |
| IC | 28570-RB876235AI |
| Flash | External SPI Flash, 512 KB minimum, memory-mapped at `0x00800000` |
| BLE radio | Integrated 2.4 GHz |
| Firmware storage | SPI flash |
| Firmware update | OTA via BLE (XMODEM protocol over Write Characteristic) |

The RTL8762C is a single-chip design. BLE communication and all dashboard application logic (speed limit enforcement, mode switching, light sensor handling) run together on this one MCU. Firmware is stored on external SPI flash and is OTA-updatable through the BLE interface — though the bootloader enforces an integrity check that rejects any modified binary.

---

## Internal Wiring — Dashboard to Controller Cable

A 5-wire cable connects the dashboard unit to the motor controller inside the deck.

| Wire Color | Function | Measured Voltage | Notes |
|-----------|----------|-----------------|-------|
| Black | GND | 0 V | Common ground |
| Red | VCC Battery | 53.04 V | **DANGER — battery voltage, do NOT connect to MCU** |
| Blue | VCC Dashboard | 52.2 V | **DANGER — battery voltage, do NOT connect to MCU** |
| Yellow | Unknown signal | 3.76 V | Purpose unclear; possibly a wake or enable line |
| Green | UART data | 4.12 V (idle) | 19200 baud, 8N1, bidirectional; this is the debug/communication line |

**Warning:** The red and blue wires carry full battery voltage (50 V+). Connecting either of these to a microcontroller, USB-UART adapter, or any 3.3 V / 5 V logic device will destroy the device instantly. Always measure with a multimeter before making any connection. Only the green signal wire and black GND wire are safe to interface with external hardware.

The green wire is the active UART data line. In normal operation the dashboard transmits speed commands and status to the motor controller over this wire at 19200 baud, 8N1. The yellow wire has been measured and logged but its function has not been confirmed — it does not carry UART data.

See [INTERNAL_UART_PROTOCOL.md](../archive/INTERNAL_UART_PROTOCOL.md) for the full frame format used on this wire.

---

## Motor Controller

| Property | Value |
|----------|-------|
| Location | Inside the deck, potted in resin |
| Accessibility | Not accessible without destructive disassembly |
| Communication | UART at 19200 baud via the green wire |
| Speed limit | Hardcoded in controller firmware |
| SWD / JTAG | Not accessible due to potting compound |

The motor controller is completely encapsulated in potting resin. Physical access to its internals requires destructive disassembly that cannot be reversed. The controller communicates with the dashboard over UART, but testing has shown that it does not take speed commands from the dashboard — the speed limit is enforced entirely within the controller's own firmware. Manipulating the dashboard's UART output (for example via an Arduino man-in-the-middle) does not affect the enforced top speed.

For the full account of UART man-in-the-middle testing, see [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md#ansatz-2-uart-man-in-the-middle--gescheitert).

---

## Battery

| Property | Value |
|----------|-------|
| Chemistry | Lithium-ion |
| Cell color | Blue (visible inside deck) |
| Nominal voltage | ~53 V |
| Connector | Internal, with manual disconnect via Wago clamps |

The battery pack is accessible inside the deck. A manual disconnect via Wago clamp connectors is possible without special tools, which is useful for safe working conditions during hardware modification. Always disconnect the battery before making any electrical connections to the dashboard or wiring harness.

---

## Speed Limiter Cable — Older Revisions

Early hardware revisions of the ST3 Pro included a dedicated white wire used as a physical speed limiter. Cutting this wire removed the speed cap on those units.

**Current revisions (2024 and later) do not have this wire.** The speed limit on current hardware is enforced entirely in firmware — there is no physical wire to cut. Attempts to bypass the limit must target the firmware directly.

Source: rollerplausch.com community forum, multiple confirmed user reports.

---

## RTL8762C Download Mode

The RTL8762C supports a UART-based download mode that allows reading and writing the entire SPI flash, bypassing the OTA bootloader completely. This is the only confirmed method to apply a patched firmware binary to the current hardware revision.

| Property | Value |
|----------|-------|
| Activation | Hold pin P0_3 LOW during boot |
| Download baud rate | 115200 |
| Normal operation baud rate | 19200 |
| Tool | [rtltool](https://github.com/wuwbobo2021/rtltool) |
| Logic level | **3.3 V — do NOT use a 5 V UART adapter** |
| Required hardware | USB-UART adapter (3.3 V), access to P0_3 pad on PCB, GND |

### Verified download mode procedure

The following setup was confirmed to work during the successful 512 KB flash dump:

- **Power supply:** Arduino board providing regulated 3.3V to the dashboard PCB (scooter battery fully disconnected). Do not attempt this with battery connected.
- **USB-UART adapter:** CP2102-based adapter at 3.3V logic level. Do not use a 5V adapter.
- **P0_3 activation:** Jumper wire from P0_3 pad to GND, held in place before and during power-on.

**Step-by-step:**

1. Disconnect the scooter battery completely.
2. Open the dashboard enclosure and locate the UART TX/RX pads, GND, and P0_3 test pad on the PCB.
3. Connect the CP2102 adapter: TX to RX pad, RX to TX pad, GND to GND.
4. Connect the Arduino 3.3V and GND pins to the dashboard 3.3V and GND pads.
5. Bridge P0_3 to GND with a jumper wire.
6. Apply power (connect Arduino USB). The RTL8762C boots into download mode.
7. Run `rtltool` commands (read flash, write flash, read MAC, etc.).
8. After the session, remove the P0_3 jumper and reboot to return to normal firmware.

For the complete step-by-step flash procedure including backup, patch application, and verification, see [SWD_FLASH_GUIDE.md](SWD_FLASH_GUIDE.md).

---

## Flash Memory Layout

The RTL8762C uses an external SPI flash chip, memory-mapped starting at `0x00800000`. The layout below is the verified layout from the actual 512 KB flash dump obtained via rtltool.

### Dual-Bank Architecture

The flash uses a dual-bank (A/B) layout for safe OTA updates. Bank A holds the currently running application firmware. Bank B (OTA staging area) holds the incoming firmware during an OTA transfer. After a successful integrity check the bootloader swaps to Bank B and Bank A becomes the next staging area. The bootloader and BLE stack patches occupy the lower address range and are not touched by OTA updates.

### Verified Layout

| Address Range | Size | Content |
|--------------|------|---------|
| `0x00800000` | — | Reserved (0xFF) |
| `0x00801000` – `0x00802FFF` | 8 KB | System config, boot parameters |
| `0x00803000` – `0x00803FFF` | 4 KB | Patch image header (BLE stack) |
| `0x00804000` – `0x0080DFFF` | 40 KB | Patch code (BLE stack, active) |
| `0x0080E000` – `0x0082FFFF` | 136 KB | App firmware — Bank A (active). Patch target at `0x0081D448` |
| `0x00840000` – `0x00841FFF` | 8 KB | OTA header area |
| `0x00844000` – `0x00865FFF` | 136 KB | OTA staging — Bank B |
| `0x00876000` | — | Additional config |

The speed limit patch point is at absolute flash address `0x0081D448` (Bank A). This was confirmed by locating the `T2202` firmware header in the dump and computing the offset of the `02 D9` branch instruction identified in Ghidra analysis. See [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md#der-patch-1-byte) for the exact 1-byte patch details.

The bootloader verifies Bank B with SHA-256 before swapping. Writing directly via download mode (rtltool) targets Bank A and bypasses this check entirely.

---

## BLE Radio

The BLE interface is the primary communication channel between the companion app and the scooter. All ride controls, telemetry, and firmware updates go through these characteristics.

| Property | Value |
|----------|-------|
| Service UUID | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Write Characteristic | `0000b002-0000-1000-8000-00805f9b34fb` |
| Notify Characteristic | `0000b003-0000-1000-8000-00805f9b34fb` |
| Advertised names | `NAVEE`, `NV`, `ST3` |
| Authentication | AES-128-ECB with 5 rotating keys |
| Scan advertisement | Service UUID not always present in scan record; direct connect by MAC address is more reliable |

The scooter does not always include the service UUID in its BLE advertisement. Connecting by stored MAC address (direct connect) is more reliable than service UUID discovery for reconnecting to a known device.

PID is encoded in the BLE scan record at bytes 6–7 (little-endian 16-bit integer). PID 23452 identifies the German market unit with the 22 km/h firmware limit.

For the complete BLE protocol including frame format, all command bytes, telemetry parsing, and the DFU update sequence, see [PROTOCOL.md](PROTOCOL.md).

For authentication key details and the auth flow, see [AUTHENTICATION.md](AUTHENTICATION.md).

---

## Photos

Photos of the opened dashboard enclosure, PCB layout, module markings, and pad locations are to be added here.

Planned additions:
- Dashboard PCB top view (module, SPI flash chip, UART pads, P0_3 test pad)
- Dashboard connector and wire harness with color labels
- Deck interior showing battery cells and motor controller potting

---

## See Also

- [PROTOCOL.md](PROTOCOL.md) — Complete BLE protocol reference
- [AUTHENTICATION.md](AUTHENTICATION.md) — Auth flow and AES keys
- [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md) — Methodology and findings, including speed limit analysis
- [SWD_FLASH_GUIDE.md](SWD_FLASH_GUIDE.md) — Step-by-step direct flash guide via RTL8762C download mode
- [INTERNAL_UART_PROTOCOL.md](../archive/INTERNAL_UART_PROTOCOL.md) — Internal UART frame format (dashboard to controller)
