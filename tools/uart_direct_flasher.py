#!/usr/bin/env python3
"""
Navee BLDC Controller — Direct UART XMODEM Flasher

Flashes BLDC controller firmware directly via UART, bypassing the dashboard.
Based on the Navee service tool "Download_Tool_S" protocol.

Hardware setup (2-Wire UART):
  - CP2102 TX  → Yellow wire (Controller RX)
  - CP2102 RX  → Green wire  (Controller TX)
  - CP2102 GND → Black wire
  - DO NOT connect Red (53V) or Blue (52V)!
  - Dashboard stays connected (for power), but Yellow wire disconnected from dashboard
  - Scooter must be powered ON (battery connected)

Usage:
  python3 uart_direct_flasher.py --detect                    # Listen for controller signals
  python3 uart_direct_flasher.py firmware.bin                # Flash firmware
  python3 uart_direct_flasher.py firmware.bin --baud 115200  # Try higher baud
  python3 uart_direct_flasher.py firmware.bin --dry-run      # Simulate without sending
"""

import argparse
import math
import struct
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("ERROR: pyserial required. Install: pip3 install pyserial")
    sys.exit(1)

XMODEM_SOH = 0x01
XMODEM_EOT = 0x04
XMODEM_ACK = 0x06
XMODEM_NAK = 0x15
XMODEM_CAN = 0x18
XMODEM_C = 0x43  # 'C' = CRC mode request

DEFAULT_BAUD = 19200
BLOCK_SIZE = 128


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def find_port():
    import glob
    for pattern in ["/dev/tty.usbserial-*", "/dev/tty.SLAB_*", "/dev/ttyUSB*"]:
        ports = glob.glob(pattern)
        if ports:
            return ports[0]
    return None


def detect_controller(port: str, baud: int, duration: float = 30.0):
    """Listen on UART for controller signals without sending anything."""
    print(f"Detecting controller on {port} at {baud} baud...")
    print(f"Listening for {duration}s — power cycle scooter if no signals appear")
    print(f"Looking for: 'C' (0x43), NAK (0x15), or Navee frames (0x64)")
    print(f"2-Wire: RX=Green (Controller TX), TX=Yellow (Controller RX)")
    print()

    ser = serial.Serial(port, baud, timeout=0.1)
    start = time.time()

    xmodem_signals = {XMODEM_C: "'C' (XMODEM CRC ready)", XMODEM_NAK: "NAK (XMODEM checksum ready)",
                      XMODEM_ACK: "ACK", XMODEM_SOH: "SOH"}
    navee_headers = {0x61: "Dashboard→Controller frame", 0x64: "Controller→Dashboard frame"}

    byte_count = 0
    while time.time() - start < duration:
        data = ser.read(64)
        if data:
            byte_count += len(data)
            t = time.time() - start

            for i, b in enumerate(data):
                if b in xmodem_signals:
                    ctx = " ".join(f"{x:02X}" for x in data[max(0, i - 2):min(len(data), i + 5)])
                    print(f"  [{t:5.1f}s] *** {xmodem_signals[b]} *** byte={byte_count - len(data) + i}")
                    print(f"          Context: {ctx}")

                if b in navee_headers:
                    ctx = " ".join(f"{x:02X}" for x in data[i:min(len(data), i + 16)])
                    print(f"  [{t:5.1f}s] Navee: {navee_headers[b]}")
                    print(f"          {ctx}")
                    break  # Don't report every byte in a Navee frame

            # Also check for text responses
            try:
                text = data.decode('ascii', errors='replace')
                if any(kw in text.lower() for kw in ['ok', 'error', 'dfu', 'ready']):
                    print(f"  [{t:5.1f}s] TEXT: {text.strip()!r}")
            except:
                pass

    ser.close()
    print(f"\nDone. Received {byte_count} bytes in {duration}s ({byte_count / duration:.0f} B/s)")


def flash_firmware(port: str, baud: int, firmware_path: Path, dry_run: bool = False,
                   strip_header: bool = False, init_cmd: str = None):
    """Flash firmware via UART XMODEM."""

    fw_data = firmware_path.read_bytes()
    if strip_header:
        print(f"Stripping 16-byte Navee header")
        fw_data = fw_data[16:]

    total_blocks = math.ceil(len(fw_data) / BLOCK_SIZE)

    print(f"Firmware: {firmware_path.name}")
    print(f"Size:     {len(fw_data)} bytes")
    print(f"Blocks:   {total_blocks}")
    print(f"Port:     {port}")
    print(f"Baud:     {baud}")
    if dry_run:
        print(f"Mode:     *** DRY RUN ***")
    print()

    if dry_run:
        print("DRY RUN: Would send firmware. Exiting.")
        return True

    ser = serial.Serial(port, baud, timeout=3.0)

    # --- Phase 1: Init ---
    if init_cmd:
        print(f"Sending init command: {init_cmd!r}")
        ser.write(init_cmd.encode('ascii'))
        time.sleep(1.0)
        resp = ser.read(64)
        if resp:
            print(f"  Response: {' '.join(f'{b:02X}' for b in resp)}")
            try:
                print(f"  Text: {resp.decode('ascii', errors='replace').strip()!r}")
            except:
                pass
        else:
            print("  No response")
        print()

    # --- Phase 2: Wait for XMODEM ready signal ---
    print("Waiting for controller XMODEM ready signal ('C' or NAK)...")
    print("(Power cycle scooter if no signal within 30s)")

    ready = False
    use_crc = True
    start = time.time()

    while time.time() - start < 60:
        data = ser.read(1)
        if data:
            b = data[0]
            if b == XMODEM_C:
                print(f"  Received 'C' (0x43) — CRC mode ready!")
                use_crc = True
                ready = True
                break
            elif b == XMODEM_NAK:
                print(f"  Received NAK (0x15) — Checksum mode ready!")
                use_crc = False
                ready = True
                break
            else:
                # Filter echo and noise
                if b in (0x61, 0x64):
                    # Navee frame — dashboard might still be connected
                    pass
                else:
                    print(f"  Received: 0x{b:02X}")

    if not ready:
        print("\nERROR: No XMODEM ready signal received.")
        print("Tips:")
        print("  - Check wiring: CP2102 TX→Yellow, CP2102 RX→Green, GND→Black")
        print("  - Yellow wire must be disconnected from dashboard")
        print("  - Power cycle the scooter")
        print("  - Try --baud 115200")
        print("  - Try --init 'down dfu_start 2\\r'")
        ser.close()
        return False

    # --- Phase 3: XMODEM transfer ---
    print(f"\nStarting XMODEM transfer ({total_blocks} blocks, {'CRC' if use_crc else 'checksum'} mode)...")
    print()

    seq = 1
    successful = 0
    failed = 0
    start_time = time.time()

    for block_num in range(total_blocks):
        offset = block_num * BLOCK_SIZE
        block_data = fw_data[offset:offset + BLOCK_SIZE]

        # Pad last block
        if len(block_data) < BLOCK_SIZE:
            block_data += bytes([0x1A] * (BLOCK_SIZE - len(block_data)))

        # Build XMODEM block
        seq_comp = (~seq) & 0xFF
        packet = bytearray([XMODEM_SOH, seq, seq_comp])
        packet += block_data

        if use_crc:
            crc = crc16_xmodem(block_data)
            packet += struct.pack(">H", crc)
        else:
            checksum = sum(block_data) & 0xFF
            packet.append(checksum)

        # Send and wait for response (2-Wire: no echo, clean ACK/NAK)
        max_retries = 3
        block_ok = False

        for retry in range(max_retries):
            ser.reset_input_buffer()
            ser.write(bytes(packet))

            # Wait for ACK/NAK (no echo on 2-wire UART)
            resp = ser.read(1)
            resp_byte = resp[0] if resp else None

            if resp_byte is None:
                # Timeout — try reading a bit more
                time.sleep(0.3)
                more = ser.read(1)
                resp_byte = more[0] if more else None

            if resp_byte == XMODEM_CAN:
                print(f"\n  CANCELLED by controller at block {block_num + 1}!")
                ser.close()
                return False

            if resp_byte == XMODEM_ACK:
                block_ok = True
                break
            elif resp_byte == XMODEM_NAK:
                if retry < max_retries - 1:
                    continue
            else:
                # Timeout — retry
                if retry < max_retries - 1:
                    continue

        if block_ok:
            successful += 1
            seq = (seq + 1) % 256
            if seq == 0:
                seq = 1
        else:
            failed += 1
            print(f"\n  Block {block_num + 1} FAILED after {max_retries} retries")
            if failed >= 5:
                print(f"\n  ABORT: Too many failures ({failed})")
                ser.close()
                return False

        # Progress
        pct = (block_num + 1) / total_blocks * 100
        bar_len = 30
        filled = int(bar_len * (block_num + 1) / total_blocks)
        bar = '#' * filled + '-' * (bar_len - filled)
        elapsed = time.time() - start_time
        eta = elapsed / (block_num + 1) * (total_blocks - block_num - 1) if block_num > 0 else 0
        print(f"\r  [{bar}] {pct:5.1f}% Block {block_num + 1}/{total_blocks} ETA {eta:.0f}s", end="", flush=True)

    print()
    elapsed = time.time() - start_time
    print(f"\n  Transfer complete:")
    print(f"    Blocks OK:  {successful}/{total_blocks}")
    print(f"    Failed:     {failed}")
    print(f"    Time:       {elapsed:.1f}s")
    print(f"    Rate:       {len(fw_data) / elapsed:.0f} bytes/s")

    # --- Phase 4: EOT ---
    print(f"\n  Sending EOT...")
    for i in range(5):
        ser.write(bytes([XMODEM_EOT]))
        time.sleep(0.5)
        resp = ser.read(10)
        if XMODEM_ACK in resp:
            print(f"    EOT ACK received!")
            break
        print(f"    EOT #{i + 1}/5...")

    # Check for success message
    time.sleep(2.0)
    final = ser.read(256)
    if final:
        text = final.decode('ascii', errors='replace')
        print(f"  Final response: {text.strip()!r}")
        if 'ok' in text.lower() or 'success' in text.lower():
            print(f"\n  *** FIRMWARE INSTALLED SUCCESSFULLY! ***")
        elif 'error' in text.lower() or 'fail' in text.lower():
            print(f"\n  *** FIRMWARE INSTALLATION FAILED ***")

    ser.close()
    print(f"\nDone. Power cycle the scooter to apply.")
    return successful == total_blocks


def main():
    parser = argparse.ArgumentParser(
        description="Navee BLDC Controller — Direct UART XMODEM Flasher",
        epilog="WARNING: Disconnect the dashboard before flashing!"
    )
    parser.add_argument("firmware", nargs="?", help="Firmware .bin file to flash")
    parser.add_argument("--port", default=None, help="Serial port (auto-detect if omitted)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--detect", action="store_true", help="Listen for controller signals only")
    parser.add_argument("--dry-run", action="store_true", help="Analyze firmware without sending")
    parser.add_argument("--strip-header", action="store_true", help="Strip 16-byte Navee OTA header")
    parser.add_argument("--init", default=None, help="Init command to send before XMODEM (e.g. 'down dfu_start 2\\r')")
    parser.add_argument("--duration", type=float, default=30.0, help="Detection duration in seconds")
    parser.add_argument("--legacy-green-only", action="store_true", help="Legacy mode: TX+RX both on green wire (deprecated)")
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        print("ERROR: No serial port found.")
        sys.exit(1)

    if args.detect:
        detect_controller(port, args.baud, args.duration)
        return

    if not args.firmware:
        print("ERROR: Firmware file required (or use --detect)")
        sys.exit(1)

    fw_path = Path(args.firmware)
    if not fw_path.exists():
        print(f"ERROR: File not found: {fw_path}")
        sys.exit(1)

    # Show firmware info
    data = fw_path.read_bytes()
    print(f"Firmware: {fw_path.name}")
    print(f"Size:     {len(data)} bytes ({len(data) / 1024:.1f} KB)")
    print(f"Blocks:   {math.ceil(len(data) / BLOCK_SIZE)}")
    if len(data) >= 21:
        model = data[:6].decode('latin-1', errors='replace').rstrip('\x00')
        fw_type = data[6]
        version = data[7:15].decode('latin-1', errors='replace').rstrip('\x00')
        print(f"Model:    {model}")
        print(f"Type:     0x{fw_type:02X}")
        print(f"Version:  {version}")
    print()

    success = flash_firmware(port, args.baud, fw_path, args.dry_run, args.strip_header, args.init)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
