#!/usr/bin/env python3
"""Versuche den RTL8762C ROM auszulesen (Checksummen-Funktion bei 0x601B9C)."""
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

    # Versuche verschiedene Adressbereiche zu lesen
    # ROM ist typischerweise bei 0x00000000-0x000FFFFF
    # Die Checksummen-Funktion ist bei 0x00601B9C

    for desc, addr, size in [
        ("ROM 0x00000000 (128B)", 0x00000000, 128),
        ("ROM 0x00600000 (128B)", 0x00600000, 128),
        ("ROM 0x00601B00 (256B)", 0x00601B00, 256),
        ("Flash 0x00800000 (128B)", 0x00800000, 128),  # Kontroll-Test
    ]:
        try:
            data = rtl.read_flash(addr, size)
            if data and len(data) > 0:
                is_empty = all(b == 0xFF for b in data) or all(b == 0x00 for b in data)
                preview = data[:32].hex()
                print(f"  {desc}: {len(data)}B {'(EMPTY)' if is_empty else preview}")

                if addr == 0x00601B00 and not is_empty:
                    # Speichere den ROM-Dump!
                    with open('firmware/rom_0x601B00.bin', 'wb') as f:
                        f.write(data)
                    print(f"    >>> ROM gespeichert! Checksummen-Funktion bei Offset 0x9C")
            else:
                print(f"  {desc}: Keine Daten")
        except Exception as e:
            print(f"  {desc}: FEHLER — {e}")

except Exception as e:
    print(f"FEHLER: {e}")
finally:
    try:
        rtl._assert_state(RTL8762C.ModuleState.RUN)
    except:
        pass
    com.close()
