# BLDC DFU Analysis — Complete Findings

## Part 1: APK Analysis — No Hidden Commands

### Conclusion
The official Navee APK uses the **exact same DFU protocol** for all MCU types. There is no hidden relay command, no passthrough mode, no additional BLE initialization for BLDC DFU.

### DFU Sequence (identical for all MCU types)
| Step | Command | Response |
|------|---------|----------|
| 1 | CMD 0x30 (Auth) | Status 0x00 |
| 2 | `"down dfu_start X\r"` (X=1,2,3,4) | `"ok\r"` |
| 3 | `"down ble_rand\r"` | `"ok " + cipher` |
| 4 | `"down ble_key " + decrypted + "\r"` | `"ok\r"` |
| 5 | Wait for 0x43 ('C') | XMODEM ready |
| 6 | XMODEM blocks (128 bytes + CRC-16) | ACK per block |
| 7 | EOT (0x04) | `"rsq dfu_ok\r"` |

### Update Order (DeviceFirmwareUpdateActivity.o0())
1. Screen (type 4) → 3.5s delay
2. BMS (type 3) → 3.5s delay
3. **BLDC (type 2)** → 3.5s delay
4. Meter (type 1) — always last (reboots dashboard)

### What Does NOT Exist (exhaustive search)
- No "relay" / "passthrough" / "bridge" / "forward" commands
- No UART mode switching
- No pre-DFU initialization for specific MCU types
- No separate BLE characteristic for BLDC
- No firmware repackaging or header modification
- No multi-phase DFU (single XMODEM session per MCU)
- No BMS-specific filtering applies to BLDC

## Part 2: BLDC Controller Firmware Analysis

### Speed Limiter Architecture

The BLDC controller uses a **three-layer speed limiting system**:

#### Layer 1: Region Selector (Byte 0x0011)
| Firmware | Value | Meaning |
|----------|-------|---------|
| DE (v0.0.1.5) | `0xCF` | German/EU restricted |
| Global (v0.0.1.1) | `0xB7` | International/unrestricted |

This single byte selects the regulatory region and determines which speed/PWM table is used.

#### Layer 2: PWM Scaling Table
| Offset (DE) | Offset (Global) | DE Value | Global Value | Diff |
|-------------|-----------------|----------|--------------|------|
| 0xC1F8 | 0xAEE8 | 50 | 45 | +5 |
| 0xC1FC | 0xAEEC | 45 | 40 | +5 |
| 0xC200 | 0xAEF0 | 44 | 39 | +5 |
| 0xC204 | 0xAEF4 | 62 | 56 | +6 |
| 0xC208 | 0xAEF8 | 59 | 53 | +6 |

DE values are 5-6 points lower (10-12% reduction), resulting in lower max PWM duty cycle = lower top speed.

#### Layer 3: Speed Progression Table (identical in both)
```
Offset DE: 0x4DF4, Global: 0x464C
Values: 15 17 19 21 23 25 27 29 31 33 35 (km/h, +2 increments)
```

Same mapping in both versions — the actual speed reduction comes from Layer 2 PWM scaling.

#### Country Code Table
```
Offset DE: 0xC214, Global: 0xAF04
Content: "CNESDEITAUEUUSJPFRNERUSEATNL..."
```
Maps region codes to speed/power configurations.

### Header Differences (Bytes 0x0000-0x001F)
```
DE:     54 32 33 32 34 00 02 30 30 31 35 31 30 31 30 00  T2324..00151010.
        00 CF 80 83 C4 FF FF FF FF FF FF FF FF FF FF FF

Global: 54 32 33 32 34 00 02 30 30 31 31 31 30 31 30 00  T2324..00111010.
        00 B7 80 F8 54 FF FF FF FF FF FF FF FF FF FF FF
```

Key bytes:
- 0x000A: Version digit (0x35=5 vs 0x31=1)
- **0x0011: Region byte (0xCF=DE vs 0xB7=Global)** ← THE KEY
- 0x0013-0x0014: Config (0x83 0xC4 vs 0xF8 0x54)

### MCU Identification
- No vendor strings found (STM32/GD32/MM32 all absent)
- Vector table doesn't follow standard ARM Cortex-M format
- Likely uses custom bootloader with Navee-specific header
- Firmware appears stripped/obfuscated

## Part 3: Why BLDC DFU Fails

### The Dashboard's Role
When receiving `dfu_start 2`:
1. Dashboard acknowledges (`"ok\r"`)
2. Dashboard performs key exchange
3. Dashboard sends XMODEM ready ('C')
4. Dashboard receives XMODEM blocks
5. **Dashboard validates firmware internally** (same undocumented check that blocks meter patches)
6. Dashboard would then relay to BLDC via internal UART protocol
7. **Step 5 fails** → NAK → firmware never reaches BLDC

### The Real Blocker
The same undocumented integrity check that prevents meter firmware OTA patching also prevents BLDC firmware upload. The dashboard treats ALL firmware (meter and BLDC) the same way — validates with its own algorithm before accepting.

## Part 4: Possible Approaches

### Approach A: Single-Byte Region Patch on BLDC Controller
Change byte 0x0011 from `0xCF` (DE) to `0xB7` (Global) directly on the BLDC controller's flash.
- **Pro**: Minimal change, controller uses Global speed tables
- **Con**: Requires physical access to BLDC controller (potted in resin), need to identify MCU and SWD pins

### Approach B: Flash Global BLDC Firmware via SWD
Write the complete Global firmware (v0.0.1.1) to the BLDC controller via SWD debug interface.
- **Pro**: Complete firmware replacement, proven compatible (same T2324 hardware)
- **Con**: Same physical access problem as Approach A

### Approach C: Dashboard SPI Flash Speed Byte Patch
Change byte at flash 0x81CC74 from 0x16 (22) to 0x28 (40) on the dashboard.
- **Pro**: Known working approach (rtltool), exact address verified
- **Con**: UART MitM proved controller ignores dashboard speed commands. **This approach will NOT work.**

### Approach D: Navee Service Center
Request BLDC firmware update from Navee's authorized service center.
- **Pro**: Official process, no risk
- **Con**: They may refuse or charge; may not offer Global firmware for DE market

### Approach E: Physical Controller Swap
Buy international BLDC controller from AliExpress.
- **Pro**: Guaranteed to work, no firmware hacking needed
- **Con**: Cost (~30-50€), need to desolder/swap potted unit
