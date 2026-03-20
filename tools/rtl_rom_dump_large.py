#!/usr/bin/env python3
"""Dump larger ROM areas of RTL8762C to find checksum function."""
import sys, os
sys.path.insert(0, '/tmp/rtltool')
import serial
from rtl8762c.rtl8762c import RTL8762C

PORT = '/dev/cu.usbserial-0001'
com = serial.Serial(PORT)
rtl = RTL8762C(com)

try:
    rtl._assert_state(RTL8762C.ModuleState.FLASH)
    print(f"Flash Size: {rtl._flash_size // 1024} KB")

    # Dump verschiedene ROM-Bereiche (je 4KB)
    for addr in [0x000000, 0x001000, 0x002000, 0x003000, 0x004000,
                 0x100000, 0x200000, 0x300000, 0x400000, 0x500000,
                 0x600000, 0x601000, 0x602000, 0x700000]:
        try:
            data = rtl.read_flash(addr, 256)
            empty = all(b == 0xFF for b in data) or all(b == 0x00 for b in data)
            if not empty:
                print(f"  0x{addr:06X}: DATA — {data[:24].hex()}")
            else:
                val = data[0]
                print(f"  0x{addr:06X}: empty (0x{val:02X})")
        except Exception as e:
            print(f"  0x{addr:06X}: ERROR — {e}")

    # Größerer Dump des Bereichs der Daten hat (0x600000)
    print(f"\nDumpe 0x600000-0x604000 (16 KB)...")
    rom_data = rtl.read_flash(0x600000, 0x4000)

    non_ff = sum(1 for b in rom_data if b != 0xFF)
    print(f"  Gelesen: {len(rom_data)} Bytes, {non_ff} non-0xFF")

    with open('firmware/rom_0x600000_16k.bin', 'wb') as f:
        f.write(rom_data)
    print(f"  Gespeichert: firmware/rom_0x600000_16k.bin")

except Exception as e:
    print(f"FEHLER: {e}")
finally:
    try:
        rtl._assert_state(RTL8762C.ModuleState.RUN)
    except:
        pass
    com.close()
