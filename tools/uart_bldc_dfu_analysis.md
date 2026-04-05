# UART BLDC DFU Analysis

## Status: PENDING — Capture not yet performed

## Goal

Determine what the dashboard sends over UART when BLDC DFU (MCU type 2) is active.
The BLE→UART relay is a black box — we need to see the actual bytes on the wire.

## Setup

```
Mac (BLE) ──BLE──> Dashboard (RTL8762C) ──UART──> BLDC Controller
                          │
                    CP2102 RXD (sniffing)
                    CP2102 GND ── black wire
```

### Wiring
- CP2102 RXD → green wire (UART data line, parallel tap — do NOT cut)
- CP2102 GND → black wire (scooter ground)
- CP2102 TXD → NOT connected (read-only sniffing)

### UART Parameters
- Baud: 19200
- Data: 8 bits, no parity, 1 stop bit
- Logic level: ~4V (non-standard, but CP2102 tolerates it)

## Procedure

### Step 1: Baseline Capture
```bash
python3 tools/uart_bldc_sniffer.py --baseline 10
```
Record 10 seconds of normal UART traffic. Expected: Frame A (~5/s), Frame B (~3/s), Frame C (~1/s).

### Step 2: BLDC DFU Capture
Terminal 1:
```bash
python3 tools/uart_bldc_sniffer.py
```

Terminal 2:
```bash
python3 tools/ota_flasher.py \
    "firmware/navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin" \
    --device-id 880002982db1
```

### Step 3: Analysis

Compare baseline vs DFU capture:
- New frame types?
- XMODEM bytes on UART?
- DFU text commands on UART?
- Data volume change?
- Timing changes?

## Known UART Frame Format

| Direction | Header | Footer | XOR |
|-----------|--------|--------|-----|
| Dashboard → Controller | 0x61 | 0x9E | 0xFF |
| Controller → Dashboard | 0x64 | 0x9B | 0xFF |

### Normal Frames
- **Frame A** (0x30): Dashboard status, 15 bytes, ~5x/sec
- **Frame B** (0x31): Dashboard telemetry, 14 bytes, ~3x/sec  
- **Frame C** (0x26): Controller telemetry, 18 bytes, ~1x/sec
- **Mode ACK** (0x23): Controller FW version + temp

Checksum: SUM(all bytes before checksum) & 0xFF

## Hypotheses

1. **Dashboard relays XMODEM blocks raw** → We should see SOH (0x01) on UART
2. **Dashboard wraps in Navee UART frame** → New CMD byte with XMODEM data inside
3. **Dashboard sends nothing** → UART is silent during DFU (relay not implemented)
4. **Dashboard uses different protocol** → Completely new frame format
5. **Baud rate changes** → Dashboard switches to higher baud for DFU transfer

## Results

*To be filled after capture*

## Next Steps

*To be determined based on results*
