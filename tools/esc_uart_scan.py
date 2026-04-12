#!/usr/bin/env python3
"""
Navee ST3 Pro ESC Board — UART Baudrate Scanner

Scans all common baudrates on a CP2102 adapter, listens for data,
and identifies which baudrate produces readable output.

Usage:
  python3 tools/esc_uart_scan.py                    # Auto-detect port
  python3 tools/esc_uart_scan.py --port /dev/tty.*  # Specific port
  python3 tools/esc_uart_scan.py --duration 5       # 5s per baud

Power cycle the ESC board during the scan to capture boot messages!
"""

import argparse
import glob
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pip3 install pyserial")
    sys.exit(1)

BAUDRATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
LOG_FILE = Path(__file__).parent / "esc_uart_scan.log"


def find_port():
    for pattern in ["/dev/tty.usbserial-*", "/dev/tty.SLAB_*", "/dev/tty.usbmodem*", "/dev/ttyUSB*"]:
        ports = glob.glob(pattern)
        if ports:
            return ports[0]
    return None


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
    return printable / len(data)


def scan_baudrate(port: str, baud: int, duration: float, log) -> dict:
    result = {"baud": baud, "bytes": 0, "printable_ratio": 0.0, "data": b"", "text": ""}

    try:
        ser = serial.Serial(port, baud, timeout=0.5)
        ser.reset_input_buffer()
    except Exception as e:
        print(f"  ERROR: {e}")
        return result

    start = time.time()
    all_data = bytearray()

    while time.time() - start < duration:
        chunk = ser.read(256)
        if chunk:
            all_data.extend(chunk)

    ser.close()

    result["bytes"] = len(all_data)
    result["data"] = bytes(all_data)
    result["printable_ratio"] = printable_ratio(all_data)

    if all_data:
        try:
            result["text"] = all_data.decode("ascii", errors="replace")
        except:
            result["text"] = ""

    # Log
    log.write(f"\n{'='*60}\n")
    log.write(f"Baudrate: {baud}\n")
    log.write(f"Bytes:    {len(all_data)}\n")
    log.write(f"Readable: {result['printable_ratio']*100:.1f}%\n")
    if all_data:
        log.write(f"Hex:      {' '.join(f'{b:02X}' for b in all_data[:100])}\n")
        if result["printable_ratio"] > 0.3:
            log.write(f"Text:     {result['text'][:200]}\n")
    log.write(f"{'='*60}\n")
    log.flush()

    return result


def main():
    parser = argparse.ArgumentParser(description="ESC Board UART Scanner")
    parser.add_argument("--port", default=None)
    parser.add_argument("--duration", type=float, default=3.0, help="Seconds per baudrate")
    parser.add_argument("--baud", type=int, default=None, help="Test single baudrate only")
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        print("ERROR: No serial port found")
        sys.exit(1)

    bauds = [args.baud] if args.baud else BAUDRATES

    print(f"ESC UART Scanner")
    print(f"Port:     {port}")
    print(f"Duration: {args.duration}s per baudrate")
    print(f"Bauds:    {len(bauds)} to test")
    print(f"Log:      {LOG_FILE}")
    print()
    print(">>> POWER CYCLE the ESC board during scan to capture boot log! <<<")
    print()

    log = open(LOG_FILE, "w")
    log.write(f"ESC UART Scan — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log.write(f"Port: {port}\n")

    results = []
    for i, baud in enumerate(bauds):
        print(f"[{i+1}/{len(bauds)}] {baud:>7} baud ... ", end="", flush=True)
        r = scan_baudrate(port, baud, args.duration, log)
        results.append(r)

        if r["bytes"] == 0:
            print("no data")
        elif r["printable_ratio"] > 0.7:
            print(f"{r['bytes']} bytes, {r['printable_ratio']*100:.0f}% readable *** MATCH! ***")
            # Show text preview
            preview = r["text"].strip()[:120].replace("\n", "\\n").replace("\r", "")
            if preview:
                print(f"         >>> {preview}")
        elif r["printable_ratio"] > 0.3:
            print(f"{r['bytes']} bytes, {r['printable_ratio']*100:.0f}% readable (partial)")
        else:
            print(f"{r['bytes']} bytes, {r['printable_ratio']*100:.0f}% readable (garbage)")

    # Summary
    print(f"\n{'='*50}")
    print(f"RESULTS")
    print(f"{'='*50}")

    matches = [r for r in results if r["printable_ratio"] > 0.7 and r["bytes"] > 0]
    partial = [r for r in results if 0.3 < r["printable_ratio"] <= 0.7 and r["bytes"] > 0]
    active = [r for r in results if r["bytes"] > 0]

    if matches:
        print(f"\nBEST MATCH:")
        for r in sorted(matches, key=lambda x: x["bytes"], reverse=True):
            print(f"  {r['baud']} baud — {r['bytes']} bytes, {r['printable_ratio']*100:.0f}% readable")
            preview = r["text"].strip()[:200].replace("\r", "")
            if preview:
                print(f"  Text: {preview[:150]}")
    elif partial:
        print(f"\nPARTIAL MATCHES (might be correct baud with binary protocol):")
        for r in partial:
            print(f"  {r['baud']} baud — {r['bytes']} bytes, {r['printable_ratio']*100:.0f}% readable")
    elif active:
        print(f"\nACTIVE (data received, but not readable text):")
        for r in active:
            print(f"  {r['baud']} baud — {r['bytes']} bytes")
            print(f"  Hex: {' '.join(f'{b:02X}' for b in r['data'][:32])}")
    else:
        print(f"\nNO DATA RECEIVED on any baudrate!")
        print(f"Check wiring: CP2102 RX → Board TX0, CP2102 GND → Board GND")

    log.close()
    print(f"\nFull log: {LOG_FILE}")


if __name__ == "__main__":
    main()
