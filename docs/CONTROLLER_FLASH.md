# BLDC Motor Controller — Flash Read/Write Guide

## Controller Location
The BLDC motor controller is inside the scooter deck, encapsulated in potting resin. Physical access requires removing the controller from the deck and carefully removing the resin to expose the PCB and MCU.

## MCU Identification

The MCU vendor is unknown (no vendor strings in firmware). Candidates based on E-Scooter industry:

| MCU | Vendor | Core | Flash | SWD Pins | Notes |
|-----|--------|------|-------|----------|-------|
| STM32F103 | ST | Cortex-M3 | 64-128KB | SWDIO, SWCLK | Most common in Chinese BLDC controllers |
| GD32F103 | GigaDevice | Cortex-M3 | 64-128KB | SWDIO, SWCLK | Pin-compatible STM32 clone |
| MM32SPIN | MindMotion | Cortex-M0 | 64-128KB | SWDIO, SWCLK | Found in K100 BLDC firmware header |
| AT32F403 | Artery | Cortex-M4 | 256KB | SWDIO, SWCLK | Higher-end controllers |

**K100 BLDC firmware header contains "MM32SPIN"** — the ST3 Pro may use the same or similar chip.

## Hardware Required
- ST-Link V2 clone (~5€ from AliExpress)
- 4 jumper wires (SWDIO, SWCLK, GND, 3.3V)
- Soldering iron (for connecting to SWD pads)
- Heat gun (optional, for removing potting resin)

## SWD Pinout (typical for all Cortex-M)
```
ST-Link V2          Controller MCU
  SWDIO  ──────────  SWDIO (PA13 on STM32)
  SWCLK  ──────────  SWCLK (PA14 on STM32)
  GND    ──────────  GND
  3.3V   ──────────  VCC (3.3V)
```

**WARNING**: Do NOT connect 3.3V if the controller is powered by the scooter battery. Use only GND + SWDIO + SWCLK when battery is connected.

## Software: OpenOCD

### Install
```bash
brew install openocd
```

### STM32F103 / GD32F103
```bash
# Connect and identify
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg

# In separate terminal:
telnet localhost 4444

# Read flash (128KB)
flash read_image controller_dump.bin 0x08000000 0x20000

# Write Global firmware
flash write_image erase navee_bldc_v0.0.1.1_ST3_Global.bin 0x08000000

# Verify
verify_image navee_bldc_v0.0.1.1_ST3_Global.bin 0x08000000
```

### MM32SPIN (MindMotion)
```bash
# MM32 uses similar debug interface but may need custom config
openocd -f interface/stlink.cfg -c "transport select swd" \
    -c "adapter speed 1000" \
    -c "set CHIPNAME mm32spin" \
    -f target/swj-dp.tcl

# Or try STM32 config (often compatible)
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg
```

### Read-Protect Check
Many controllers have flash read protection enabled. Check with:
```bash
# In OpenOCD telnet:
stm32f1x options_read 0
# If RDP is set, flash cannot be read (but can be mass-erased)
```

If read-protected:
- **Cannot read** existing firmware
- **CAN write** new firmware (but must mass-erase first, losing original)
- Keep the Global firmware file ready before erasing!

## Speed Patch Options

### Option 1: Flash Complete Global Firmware
Replace entire BLDC firmware with Global version (v0.0.1.1):
```bash
flash write_image erase tools/firmware/navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin 0x08000000
```
**Note**: The firmware file includes a 16-byte Navee header that may need to be stripped:
```bash
# Strip 16-byte Navee header first
dd if=navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin of=bldc_global_raw.bin bs=1 skip=16
# Then flash
flash write_image erase bldc_global_raw.bin 0x08000000
```

### Option 2: Single-Byte Region Patch
Change region byte from DE (0xCF) to Global (0xB7):
```bash
# Read sector containing byte 0x0011
flash read_image sector.bin 0x08000000 0x1000

# Patch byte 0x11 from 0xCF to 0xB7
python3 -c "
d = bytearray(open('sector.bin','rb').read())
assert d[0x11] == 0xCF, f'Expected 0xCF, got 0x{d[0x11]:02X}'
d[0x11] = 0xB7
open('sector_patched.bin','wb').write(d)
print('Patched: 0xCF → 0xB7')
"

# Write back
flash write_image erase sector_patched.bin 0x08000000
```

## BLDC Firmware Files Available

| File | Version | Region | Size | SHA-256 (first 8) |
|------|---------|--------|------|-------------------|
| `navee_bldc_v0.0.1.5_ST3_PRO_DE_*.bin` | v0.0.1.5 | DE (22 km/h) | 53,376 | 6d0e5cd8 |
| `navee_bldc_v0.0.1.1_ST3_Global_*.bin` | v0.0.1.1 | Global | 47,232 | 14f86f81 |

Both use hardware model `T2324` — confirmed compatible.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| MCU read-protected | High | Have Global firmware ready before mass-erase |
| Wrong MCU identified | Medium | Try STM32 config first, then MM32 |
| SWD pins damaged | Low | Use fine soldering, don't force connections |
| Potting resin damage | Medium | Use heat gun carefully, acetone for cleanup |
| Controller bricked | Low | Can always flash known-good firmware via SWD |
| Scooter warranty void | Certain | Opening controller voids warranty |
