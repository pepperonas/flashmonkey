#!/usr/bin/env python3
"""RTL8762C Flash Dump — liest den kompletten SPI Flash aus."""
import sys, os
sys.path.insert(0, '/tmp/rtltool')
import serial
from rtl8762c.rtl8762c import RTL8762C

PORT = '/dev/cu.usbserial-0001'
OUTPUT = 'firmware/navee_full_flash_dump.bin'
FLASH_START = 0x800000
FLASH_SIZE = 0x80000  # 512 KB

print(f"Port: {PORT}")
print(f"Output: {OUTPUT}")
print(f"Flash: 0x{FLASH_START:X} - 0x{FLASH_START+FLASH_SIZE:X} ({FLASH_SIZE//1024} KB)")

com = serial.Serial(PORT)
rtl = RTL8762C(com)

try:
    rtl._assert_state(RTL8762C.ModuleState.FLASH)
    print(f"Flash Size: {rtl._flash_size // 1024} KB")
    print("Starte Flash-Dump...")

    data = rtl.read_flash(FLASH_START, FLASH_SIZE)
    print(f"Gelesen: {len(data)} Bytes")

    os.makedirs(os.path.dirname(OUTPUT) or '.', exist_ok=True)
    with open(OUTPUT, 'wb') as f:
        f.write(data)

    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    print(f"SHA-256: {sha}")
    print(f"DUMP GESPEICHERT: {OUTPUT}")

except Exception as e:
    print(f"FEHLER: {e}")
finally:
    try:
        rtl._assert_state(RTL8762C.ModuleState.RUN)
    except:
        pass
    com.close()
