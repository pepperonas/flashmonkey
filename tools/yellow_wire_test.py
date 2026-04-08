#!/usr/bin/env python3
"""
Yellow Wire Test: Is the yellow wire a separate Controller RX input?

Setup (single CP2102):
  CP2102 TX  → Yellow wire (testing if Controller RX)
  CP2102 RX  → Green wire  (monitoring Controller responses)
  CP2102 GND → Black wire

Phase 1: Baseline — listen only on Green (5s)
Phase 2: Frame injection on Yellow, monitor Green (10s)
Phase 3: DFU trigger commands on Yellow, monitor Green (10s)
"""

import glob
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pip3 install pyserial")
    sys.exit(1)

BAUD = 19200
LOG_FILE = Path(__file__).parent / "yellow_wire_injection_test.log"


def find_port():
    for pattern in ["/dev/tty.usbserial-*", "/dev/tty.SLAB_*", "/dev/ttyUSB*"]:
        ports = glob.glob(pattern)
        if ports:
            return ports[0]
    return None


def calc_checksum(frame_bytes):
    return sum(frame_bytes) & 0xFF


def build_frame_a(mode=0x33, light=0x04, speed_a=0x28, speed_b=0x28):
    """Build a Dashboard→Controller Frame A (0x61)."""
    frame = [0x61, 0x30, 0x0A, mode, light, 0x88, speed_a, speed_b, 0x01, 0x00, 0x00, 0x00, 0x00]
    chk = calc_checksum(frame)
    return bytes(frame + [chk, 0x9E])


def parse_frames(data):
    """Extract Navee frames from raw bytes."""
    frames = []
    i = 0
    while i < len(data):
        if data[i] == 0x61 and i + 2 < len(data):
            # Frame A/B: 61 XX LEN ... 9E
            length = data[i + 2] if i + 2 < len(data) else 0
            end = i + 3 + length + 2  # header(3) + data(length) + checksum(1) + footer(1)
            if end <= len(data):
                frames.append(("TX" if data[i + 1] in (0x30, 0x31) else "??", bytes(data[i:end])))
                i = end
                continue
        elif data[i] == 0x64 and i + 2 < len(data):
            # Frame C: 64 XX LEN ... 9B
            length = data[i + 2] if i + 2 < len(data) else 0
            end = i + 3 + length + 2
            if end <= len(data):
                frames.append(("RX", bytes(data[i:end])))
                i = end
                continue
        i += 1
    return frames


def frame_hex(data, max_bytes=20):
    s = " ".join(f"{b:02X}" for b in data[:max_bytes])
    if len(data) > max_bytes:
        s += " ..."
    return s


def log_and_print(log, msg):
    print(msg)
    log.write(msg + "\n")
    log.flush()


def collect_frames(ser, duration, log, label=""):
    """Read from serial for `duration` seconds, return list of (timestamp, type, frame_bytes)."""
    results = []
    start = time.time()
    buf = bytearray()

    while time.time() - start < duration:
        data = ser.read(128)
        if data:
            t = time.time() - start
            buf.extend(data)

            # Try to parse complete frames from buffer
            frames = parse_frames(buf)
            if frames:
                for ftype, fbytes in frames:
                    results.append((t, ftype, fbytes))
                    if ftype == "RX":
                        log_and_print(log, f"  [{t:5.1f}s] {label} 0x64 {frame_hex(fbytes)}")
                # Remove parsed bytes (simplified: clear buffer after parsing)
                # Find last frame end in buffer
                buf.clear()

    return results


def main():
    port = find_port()
    if not port:
        print("ERROR: No serial port found")
        sys.exit(1)

    print(f"Port: {port}")
    print(f"Baud: {BAUD}")
    print(f"Log:  {LOG_FILE}")
    print()

    ser = serial.Serial(port, BAUD, timeout=0.1)
    log = open(LOG_FILE, "w")

    log_and_print(log, f"Yellow Wire Injection Test — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log_and_print(log, f"Port: {port}, Baud: {BAUD}")
    log_and_print(log, "")

    # === PHASE 1: Baseline ===
    log_and_print(log, "=" * 60)
    log_and_print(log, "  PHASE 1: Baseline — Listen only on Green (5s)")
    log_and_print(log, "=" * 60)
    log_and_print(log, "  Not sending anything. Recording Controller→Dashboard frames.")
    log_and_print(log, "")

    ser.reset_input_buffer()
    baseline_frames = collect_frames(ser, 5.0, log, label="BASELINE")

    baseline_64 = [f for f in baseline_frames if f[1] == "RX"]
    log_and_print(log, f"\n  Baseline: {len(baseline_frames)} total frames, {len(baseline_64)} are 0x64 (Controller→Dashboard)")

    if baseline_64:
        log_and_print(log, f"  Reference 0x64 frame: {frame_hex(baseline_64[0][2])}")
        # Extract key bytes for comparison
        ref = baseline_64[0][2]
        log_and_print(log, f"  Reference bytes [3:8]: {' '.join(f'{b:02X}' for b in ref[3:8] if len(ref) > 7)}")
    else:
        log_and_print(log, "  WARNING: No 0x64 frames in baseline! Controller may not be responding.")

    log_and_print(log, "")
    time.sleep(0.5)

    # === PHASE 2: Frame Injection ===
    log_and_print(log, "=" * 60)
    log_and_print(log, "  PHASE 2: Frame Injection on Yellow (10s)")
    log_and_print(log, "=" * 60)

    # Build injection frame: SPORT mode, light ON, speed 40/40
    inject_frame = build_frame_a(mode=0x33, light=0x04, speed_a=0x28, speed_b=0x28)
    log_and_print(log, f"  Injecting Frame A: {frame_hex(inject_frame)}")
    log_and_print(log, f"  Mode=SPORT(0x33), Light=ON(0x04), Speed=40/40(0x28/0x28)")
    log_and_print(log, f"  Rate: 5 frames/sec for 10 seconds")
    log_and_print(log, "")

    ser.reset_input_buffer()
    inject_frames = []
    inject_count = 0
    start = time.time()
    buf = bytearray()
    next_send = start

    while time.time() - start < 10.0:
        now = time.time()
        t = now - start

        # Send injection frame at 5 Hz
        if now >= next_send:
            ser.write(inject_frame)
            inject_count += 1
            next_send += 0.2  # 200ms = 5Hz
            if inject_count <= 3 or inject_count % 10 == 0:
                log_and_print(log, f"  [{t:5.1f}s] SENT #{inject_count}: {frame_hex(inject_frame)}")

        # Read responses
        data = ser.read(128)
        if data:
            buf.extend(data)
            frames = parse_frames(buf)
            for ftype, fbytes in frames:
                inject_frames.append((t, ftype, fbytes))
                if ftype == "RX":
                    log_and_print(log, f"  [{t:5.1f}s] RESPONSE 0x64: {frame_hex(fbytes)}")
            if frames:
                buf.clear()

    inject_64 = [f for f in inject_frames if f[1] == "RX"]
    log_and_print(log, f"\n  Injection: sent {inject_count} frames, received {len(inject_frames)} total, {len(inject_64)} are 0x64")

    # Compare with baseline
    if baseline_64 and inject_64:
        ref_bytes = baseline_64[0][2]
        changed = False
        for _, _, fb in inject_64:
            if len(fb) == len(ref_bytes):
                diffs = [(i, ref_bytes[i], fb[i]) for i in range(len(fb)) if ref_bytes[i] != fb[i]]
                if diffs:
                    changed = True
                    diff_str = ", ".join(f"byte[{i}]: {old:02X}→{new:02X}" for i, old, new in diffs[:5])
                    log_and_print(log, f"  *** CHANGE DETECTED: {diff_str}")
            elif len(fb) != len(ref_bytes):
                changed = True
                log_and_print(log, f"  *** DIFFERENT FRAME LENGTH: baseline={len(ref_bytes)}, response={len(fb)}")

        if not changed:
            log_and_print(log, "  No changes in 0x64 frames compared to baseline.")
    else:
        log_and_print(log, "  Cannot compare — missing baseline or response frames.")

    log_and_print(log, "")
    time.sleep(1.0)

    # === PHASE 3: DFU Triggers ===
    log_and_print(log, "=" * 60)
    log_and_print(log, "  PHASE 3: DFU Trigger Commands on Yellow (10s)")
    log_and_print(log, "=" * 60)

    dfu_commands = [
        ("down dfu_start 2\\r", b"down dfu_start 2\r"),
        ("down dfu_start\\r", b"down dfu_start\r"),
        ("'C' (0x43)", bytes([0x43])),
        ("SOH block (XMODEM init)", bytes([0x01, 0x01, 0xFE]) + bytes(128) + bytes([0x00, 0x00])),
    ]

    for cmd_name, cmd_bytes in dfu_commands:
        log_and_print(log, f"\n  --- Sending: {cmd_name} ---")
        log_and_print(log, f"  Hex: {frame_hex(cmd_bytes, max_bytes=30)}")

        ser.reset_input_buffer()
        ser.write(cmd_bytes)

        # Listen for 3 seconds
        start_cmd = time.time()
        got_response = False
        while time.time() - start_cmd < 3.0:
            data = ser.read(64)
            if data:
                t = time.time() - start_cmd
                got_response = True
                hex_str = " ".join(f"{b:02X}" for b in data[:32])
                log_and_print(log, f"  [{t:5.1f}s] GOT: {hex_str}")

                # Check for XMODEM signals
                for b in data:
                    if b == 0x43:
                        log_and_print(log, f"  *** 'C' (0x43) DETECTED — XMODEM CRC READY! ***")
                    elif b == 0x06:
                        log_and_print(log, f"  *** ACK (0x06) DETECTED! ***")
                    elif b == 0x15:
                        log_and_print(log, f"  *** NAK (0x15) DETECTED! ***")

                # Check for text
                try:
                    text = data.decode('ascii', errors='replace').strip()
                    if any(kw in text.lower() for kw in ['ok', 'error', 'dfu', 'ready', 'boot']):
                        log_and_print(log, f"  *** TEXT: {text!r} ***")
                except:
                    pass

        if not got_response:
            log_and_print(log, "  No response (3s timeout)")

    # === SUMMARY ===
    log_and_print(log, "")
    log_and_print(log, "=" * 60)
    log_and_print(log, "  SUMMARY")
    log_and_print(log, "=" * 60)

    has_baseline = len(baseline_64) > 0
    has_inject_response = len(inject_64) > 0

    if has_baseline and has_inject_response:
        ref_bytes = baseline_64[0][2]
        any_change = False
        for _, _, fb in inject_64:
            if len(fb) == len(ref_bytes) and fb != ref_bytes:
                any_change = True
                break
            elif len(fb) != len(ref_bytes):
                any_change = True
                break

        if any_change:
            log_and_print(log, "  RESULT: Controller RESPONDED to Yellow wire injection!")
            log_and_print(log, "  >>> YELLOW IS CONTROLLER RX! <<<")
            log_and_print(log, "  This means we can send commands directly to the controller!")
        else:
            log_and_print(log, "  RESULT: 0x64 frames unchanged during injection.")
            log_and_print(log, "  Yellow wire is likely NOT Controller RX (or controller ignores invalid frames).")
    elif has_baseline and not has_inject_response:
        log_and_print(log, "  RESULT: Lost 0x64 frames during injection — possible bus collision.")
        log_and_print(log, "  Yellow wire TX may have disrupted Controller RX (voltage mismatch).")
    else:
        log_and_print(log, "  RESULT: Insufficient data for conclusion.")

    log_and_print(log, "")

    ser.close()
    log.close()
    print(f"\nLog saved: {LOG_FILE}")


if __name__ == "__main__":
    main()
