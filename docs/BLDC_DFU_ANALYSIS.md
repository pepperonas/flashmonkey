# BLDC DFU Analysis — Why It Fails

## Summary

BLDC DFU uses the **exact same protocol** as Meter DFU. The only difference is the command parameter (`dfu_start 2` vs `dfu_start 1`). There is no hidden relay-mode command, no separate BLE characteristic, no additional initialization step.

## APK Analysis: BLDC vs Meter DFU

### Identical Across All MCU Types
| Component | Detail |
|-----------|--------|
| BLE Service | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Write Characteristic | `0000b002-0000-1000-8000-00805f9b34fb` |
| Write Type | `WRITE_NO_RESPONSE` (setWriteType(1)) |
| Key Exchange | `ble_rand` + `ble_key` with XOR/AES |
| XMODEM Format | SOH + seq + ~seq + 128 data + CRC-16 BE |
| State Machine | sendStart → requestRand → sendRand → xmodemReady → xmodemSendPack → xmodemSendEOT → xmodemFinished |

### Only Difference
```
Meter:  "down dfu_start 1\r"
BLDC:   "down dfu_start 2\r"
BMS:    "down dfu_start 3\r"
Screen: "down dfu_start 4\r"
```

### DFU Update Order (from DeviceFirmwareUpdateActivity.o0())
1. Screen (type 4) — if firmware available
2. BMS (type 3) — if firmware available
3. BLDC (type 2) — if firmware available
4. Meter (type 1) — **always last** (reboots dashboard)

3.5 second delay between each MCU update.

### What Does NOT Exist (searched exhaustively)
- No "relay mode" or "passthrough" command
- No UART/serial mode switching
- No prepare/init phase before `dfu_start`
- No MCU-type-specific BLE commands
- No separate characteristic for BLDC
- No additional header or wrapper for BLDC firmware

## UART Sniffer Results

### During BLDC DFU (`dfu_start 2`)
- Normal Frame A/B/C traffic continues **uninterrupted**
- **Zero** XMODEM bytes appear on UART
- Dashboard does NOT relay BLE data to UART
- NAK received via BLE comes from **dashboard itself**, not BLDC controller

### During Meter DFU (`dfu_start 1`)
- Dashboard sends `"ok\r"` on UART, then **reboots**
- UART goes silent (dashboard in bootloader mode)
- After reboot: new frames CMD 0x29 (serial), 0x24 (meter ver), 0x21 (BLDC ver)

## Root Cause Analysis

The dashboard firmware (Navee app on RTL8762C) handles `dfu_start 2` by:
1. Acknowledging with `"ok\r"` via BLE ✓
2. Completing key exchange (`ble_rand`/`ble_key`) via BLE ✓
3. Sending XMODEM 'C' ready signal via BLE ✓
4. **Receiving XMODEM blocks via BLE** ✓
5. **NOT forwarding them to UART** ✗
6. **NAK'ing blocks** (validation fails internally) ✗

The dashboard tries to validate the XMODEM data itself (as if it were receiving its own firmware) instead of relaying it to the BLDC controller. The NAK on Block 1 is the dashboard rejecting the data because the firmware header says "BLDC" (type 0x02, model T2324) but the dashboard expects "Meter" (type 0x01, model T2202).

## Hypothesis: Dashboard Stores, Then Relays

The official app probably works because:
1. Dashboard receives BLDC firmware via XMODEM into **its own staging area**
2. Dashboard validates (its own checksum algorithm — which we can't replicate via OTA)
3. After validation, dashboard independently flashes the BLDC via internal UART protocol
4. Dashboard sends `rsq dfu_ok` after BLDC confirms successful flash

This two-phase approach means:
- Phase 1 (BLE → Dashboard): Uses the dashboard's OTA validation — **which rejects our modified firmware**
- Phase 2 (Dashboard → BLDC via UART): Uses internal protocol we never see

## Why Our OTA Patched Firmware Fails

The dashboard's OTA validation (Phase 1) has an **undocumented integrity check** beyond SHA-256. Even a 1-byte change with correctly recomputed SHA-256 is rejected. The Bee2 SDK `slient_dfu_check_sha256()` function matches our implementation, but the actual bootloader/app has additional validation.

This same check blocks both:
- Meter firmware patching (speed byte or NOP patch)
- BLDC firmware upload (different firmware entirely)

## Confirmed Attack Vectors Status

| Vector | Status | Reason |
|--------|--------|--------|
| BLE CMD 0x6E | Failed | Dashboard ignores without firmware patch |
| UART MitM | Failed | BLDC controller ignores manipulated frames (1168 frames tested) |
| Meter OTA Patch | Failed | Undocumented bootloader check rejects modified firmware |
| BLDC OTA Flash | Failed | Dashboard doesn't relay XMODEM to BLDC |
| SPI Flash Direct | **Works** | Bypasses all validation, writes Bank A directly |
| Controller Swap | **Works** | Physical replacement with international model |

## Next Steps

1. **SPI Flash Direct** on new dashboard (requires opening dashboard for P0_3 access)
   - Patch speed byte at flash 0x81CC74: `0x16` → `0x28` (22 → 40 km/h)
   - BUT: BLDC controller has its own speed limit (v0.0.1.5 DE firmware)
   - UART MitM proved controller ignores dashboard speed commands
   - **This may not work** because the speed limit is in the BLDC, not the dashboard

2. **BLDC Controller Physical Swap** — buy international model from AliExpress

3. **Navee Service Center** — ask for BLDC firmware update (email sent to support)
