#!/usr/bin/env python3
"""
Hybrid BLDC Flash: BLE init (dfu_start 2) + UART XMODEM data transfer.

The dashboard sends "ok\r" on UART when it receives dfu_start 2 via BLE.
This might trigger the controller's bootloader. We then send XMODEM
firmware blocks directly via UART (CP2102), bypassing the dashboard's
broken relay.

Usage:
  python3 hybrid_bldc_flash.py firmware.bin 880002982db1 /dev/tty.usbserial-0001
"""
import asyncio
import math
import struct
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pip3 install pyserial")
    sys.exit(1)

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("pip3 install bleak")
    sys.exit(1)

WRITE_UUID = "0000b002-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000b003-0000-1000-8000-00805f9b34fb"
BLOCK_SIZE = 128


def crc16(data):
    c = 0
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else c << 1
            c &= 0xFFFF
    return c


async def main():
    if len(sys.argv) < 4:
        print("Usage: python3 hybrid_bldc_flash.py <firmware.bin> <device_id> <serial_port>")
        print("Example: python3 hybrid_bldc_flash.py firmware/navee_bldc_v0.0.1.1_ST3_Global,_pid=24012.bin 880002982db1 /dev/tty.usbserial-0001")
        sys.exit(1)

    fw_path = sys.argv[1]
    device_id_hex = sys.argv[2]
    serial_port = sys.argv[3]

    fw_data = Path(fw_path).read_bytes()
    device_id = bytes.fromhex(device_id_hex)
    total_blocks = math.ceil(len(fw_data) / BLOCK_SIZE)

    print(f"Firmware: {Path(fw_path).name} ({len(fw_data)} bytes, {total_blocks} blocks)")
    print(f"Device:   {device_id_hex}")
    print(f"Serial:   {serial_port}")
    print()

    # === Phase 1: BLE — Authenticate + dfu_start 2 ===
    print("=" * 50)
    print("  Phase 1: BLE — dfu_start 2")
    print("=" * 50)

    print("Scanning for Navee scooter...")
    devices = await BleakScanner.discover(timeout=15)
    navee = [d for d in devices if (d.name or "").upper().startswith("NAVEE")]
    if not navee:
        print("No scooter found!")
        return

    addr = navee[0].address
    print(f"  Found: {navee[0].name} [{addr}]")

    client = BleakClient(addr, timeout=15)
    await client.connect()
    print("  Connected!")

    responses = []

    def on_notify(c, d):
        responses.append(bytes(d))

    await client.start_notify(NOTIFY_UUID, on_notify)

    # Authenticate
    print("  Authenticating...")
    auth = bytearray([0x55, 0xAA, 0x00, 0x30, 0x09, 0x01, 0x00])
    auth += device_id
    auth.append(0x00)
    chk = sum(auth) & 0xFF
    auth.append(chk)
    auth += b'\xFE\xFD'
    await client.write_gatt_char(WRITE_UUID, bytes(auth), response=True)
    await asyncio.sleep(1.5)

    # Check auth response
    auth_ok = any(b'\x00' in r for r in responses)
    print(f"  Auth: {'OK' if auth_ok else 'FAILED'}")
    if not auth_ok:
        await client.disconnect()
        return

    # Send dfu_start 2
    print("  Sending 'down dfu_start 2'...")
    responses.clear()
    await client.write_gatt_char(WRITE_UUID, b"down dfu_start 2\r", response=True)
    await asyncio.sleep(2.0)

    dfu_ok = any(b"ok" in r for r in responses)
    print(f"  dfu_start 2: {'OK' if dfu_ok else 'NO RESPONSE'}")

    if dfu_ok:
        print("  → Dashboard sent 'ok\\r' on UART to controller")
        print("  → Controller should be entering bootloader mode")

    # Keep BLE connected (don't disconnect — dashboard needs to stay in DFU mode)
    print()

    # === Phase 2: UART — Wait for 'C' + XMODEM ===
    print("=" * 50)
    print("  Phase 2: UART — XMODEM Transfer")
    print("=" * 50)

    print(f"Opening {serial_port} at 19200 baud (2-Wire: TX→Yellow, RX→Green)...")
    ser = serial.Serial(serial_port, 19200, timeout=1.0)

    # Wait for 'C' from controller (comes via Green = Controller TX)
    print("Waiting for controller XMODEM ready signal ('C')...")
    print("  (Reading from Green wire = Controller TX)")

    ready = False
    start = time.time()
    while time.time() - start < 30:
        data = ser.read(32)
        for b in data:
            if b == 0x43:  # 'C'
                # Filter: if surrounded by Navee frame bytes, it's not XMODEM
                # A standalone 0x43 or at start of data = XMODEM ready
                print(f"  Got 'C' (0x43) at t={time.time() - start:.1f}s!")
                ready = True
                break
        if ready:
            break

    if not ready:
        print("\n  No 'C' received from controller.")
        print("  The controller did not enter bootloader mode.")
        print("  The 'ok\\r' from dashboard was not enough to trigger it.")
        ser.close()
        await client.disconnect()
        return

    # XMODEM transfer
    print(f"\nFlashing {total_blocks} blocks via UART...")
    seq = 1
    ok_blocks = 0
    failed = 0
    t0 = time.time()

    for bn in range(total_blocks):
        offset = bn * BLOCK_SIZE
        block_data = fw_data[offset:offset + BLOCK_SIZE]
        if len(block_data) < BLOCK_SIZE:
            block_data += bytes([0x1A] * (BLOCK_SIZE - len(block_data)))

        seq_comp = (~seq) & 0xFF
        packet = bytes([0x01, seq, seq_comp]) + block_data + struct.pack(">H", crc16(block_data))

        block_ok = False
        for retry in range(3):
            ser.reset_input_buffer()
            ser.write(packet)
            time.sleep(0.05)

            # Read response
            resp = ser.read(len(packet) + 10)
            if 0x06 in resp:  # ACK
                block_ok = True
                break
            elif 0x15 in resp:  # NAK
                continue
            else:
                time.sleep(0.3)
                more = ser.read(10)
                if 0x06 in more:
                    block_ok = True
                    break

        if block_ok:
            ok_blocks += 1
        else:
            failed += 1
            if failed >= 5:
                print(f"\n  ABORT: {failed} failed blocks")
                break

        seq = (seq % 255) + 1
        pct = (bn + 1) / total_blocks * 100
        filled = int(30 * (bn + 1) / total_blocks)
        bar = '#' * filled + '-' * (30 - filled)
        elapsed = time.time() - t0
        eta = elapsed / (bn + 1) * (total_blocks - bn - 1) if bn > 0 else 0
        print(f"\r  [{bar}] {pct:5.1f}% Block {bn + 1}/{total_blocks} ETA {eta:.0f}s", end="", flush=True)

    elapsed = time.time() - t0
    print(f"\n\n  Transfer: {ok_blocks}/{total_blocks} blocks OK in {elapsed:.1f}s")

    # EOT
    print("  Sending EOT...")
    for i in range(5):
        ser.write(bytes([0x04]))
        time.sleep(0.5)
        r = ser.read(10)
        if 0x06 in r:
            print(f"  EOT ACK received!")
            break
        print(f"  EOT #{i + 1}/5...")

    # Check final response
    time.sleep(2.0)
    final = ser.read(256)
    if final:
        text = final.decode('ascii', errors='replace').strip()
        if text:
            print(f"  Final: {text!r}")

    ser.close()
    await client.disconnect()
    print("\n  Power cycle scooter to apply firmware.")


if __name__ == "__main__":
    asyncio.run(main())
