#!/usr/bin/env python3
"""
Navee ST3 Pro — UART BLDC DFU Sniffer

Mithören auf dem internen UART (19200 Baud, 8N1) zwischen Dashboard und
Motor-Controller während eines BLDC-DFU-Versuchs.

Hardware-Setup:
  - CP2102 RXD → grüne Ader (UART, parallel anklemmen)
  - CP2102 GND → schwarze Ader (Scooter GND)
  - CP2102 TXD → NICHT verbinden (nur mithören)

Usage:
  python3 uart_bldc_sniffer.py                          # Auto-detect port
  python3 uart_bldc_sniffer.py /dev/tty.usbserial-0001  # Explicit port
  python3 uart_bldc_sniffer.py --baseline 10             # 10s baseline capture
"""

import glob
import os
import signal
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
except ImportError:
    print("ERROR: pyserial required. Install: pip3 install pyserial")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "uart_bldc_dfu_capture.log"

BAUD_RATE = 19200
TIMEOUT = 0.05  # 50ms read timeout for responsive display

# Known frame headers/footers
DASH_TO_CTRL_HEADER = 0x61
DASH_TO_CTRL_FOOTER = 0x9E
CTRL_TO_DASH_HEADER = 0x64
CTRL_TO_DASH_FOOTER = 0x9B

# Known command bytes
KNOWN_CMDS = {
    0x30: "Frame A (Dashboard Status)",
    0x31: "Frame B (Dashboard Telemetry)",
    0x26: "Frame C (Controller Telemetry)",
    0x23: "Mode ACK (Controller FW/Temp)",
}

# XMODEM constants
XMODEM_SOH = 0x01
XMODEM_EOT = 0x04
XMODEM_ACK = 0x06
XMODEM_NAK = 0x15
XMODEM_CAN = 0x18
XMODEM_C = 0x43

XMODEM_NAMES = {
    XMODEM_SOH: "XMODEM SOH (Start of Header)",
    XMODEM_EOT: "XMODEM EOT (End of Transmission)",
    XMODEM_ACK: "XMODEM ACK",
    XMODEM_NAK: "XMODEM NAK",
    XMODEM_CAN: "XMODEM CAN (Cancel)",
    XMODEM_C: "XMODEM 'C' (CRC mode request)",
}

# DFU text command patterns
DFU_PATTERNS = [
    b"down dfu_start",
    b"down ble_rand",
    b"down ble_key",
    b"ok\r",
    b"rsq dfu_ok",
    b"rsq dfu_error",
]


class UARTSniffer:
    def __init__(self, port, log_path=LOG_FILE):
        self.port = port
        self.log_path = log_path
        self.log_file = None
        self.start_time = time.monotonic()
        self.byte_count = 0
        self.frame_count = 0
        self.unknown_count = 0
        self.xmodem_count = 0
        self.buffer = bytearray()
        self.running = True

        # Frame stats
        self.frame_stats = {
            "frame_a": 0,
            "frame_b": 0,
            "frame_c": 0,
            "mode_ack": 0,
            "unknown_navee": 0,
            "xmodem": 0,
            "dfu_text": 0,
            "raw_unknown": 0,
        }

    def elapsed(self):
        return time.monotonic() - self.start_time

    def log(self, msg, console=True):
        ts = f"[{self.elapsed():8.3f}]"
        line = f"{ts} {msg}"
        if console:
            print(line)
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def hex_str(self, data):
        return " ".join(f"{b:02X}" for b in data)

    def parse_navee_frame(self, data):
        """Try to parse a Navee UART frame."""
        if len(data) < 4:
            return None

        header = data[0]
        footer = data[-1]

        if header == DASH_TO_CTRL_HEADER and footer == DASH_TO_CTRL_FOOTER:
            direction = "DASH→CTRL"
        elif header == CTRL_TO_DASH_HEADER and footer == CTRL_TO_DASH_FOOTER:
            direction = "CTRL→DASH"
        else:
            return None

        cmd = data[1] if len(data) > 1 else None
        length = data[2] if len(data) > 2 else None
        checksum = data[-2] if len(data) > 3 else None

        # Verify checksum
        calc_chk = sum(data[:-2]) & 0xFF
        chk_ok = calc_chk == checksum if checksum is not None else False

        cmd_name = KNOWN_CMDS.get(cmd, f"UNKNOWN CMD 0x{cmd:02X}" if cmd else "?")

        return {
            "direction": direction,
            "cmd": cmd,
            "cmd_name": cmd_name,
            "length": length,
            "data": data,
            "checksum_ok": chk_ok,
        }

    def identify_xmodem(self, byte_val):
        """Check if a byte is an XMODEM control character."""
        return XMODEM_NAMES.get(byte_val)

    def check_dfu_text(self, data):
        """Check for DFU text commands in data."""
        for pattern in DFU_PATTERNS:
            if pattern in data:
                return pattern.decode("ascii", errors="replace")
        return None

    def process_buffer(self):
        """Process accumulated bytes, detect frames and patterns."""
        if not self.buffer:
            return

        # Check for DFU text commands first
        dfu_cmd = self.check_dfu_text(bytes(self.buffer))
        if dfu_cmd:
            self.log(f"*** DFU TEXT: '{dfu_cmd.strip()}' ***", console=True)
            self.log(f"    Raw: {self.hex_str(self.buffer)}", console=True)
            self.frame_stats["dfu_text"] += 1
            self.buffer.clear()
            return

        # Try to find Navee frames
        i = 0
        while i < len(self.buffer):
            # Look for frame start
            if self.buffer[i] in (DASH_TO_CTRL_HEADER, CTRL_TO_DASH_HEADER):
                header = self.buffer[i]
                expected_footer = DASH_TO_CTRL_FOOTER if header == DASH_TO_CTRL_HEADER else CTRL_TO_DASH_FOOTER

                # Find footer
                for j in range(i + 3, min(i + 30, len(self.buffer))):
                    if self.buffer[j] == expected_footer:
                        frame_data = bytes(self.buffer[i:j + 1])
                        parsed = self.parse_navee_frame(frame_data)
                        if parsed:
                            self.frame_count += 1
                            cmd = parsed["cmd"]
                            is_known = cmd in KNOWN_CMDS
                            chk = "OK" if parsed["checksum_ok"] else "BAD"

                            if cmd == 0x30:
                                self.frame_stats["frame_a"] += 1
                            elif cmd == 0x31:
                                self.frame_stats["frame_b"] += 1
                            elif cmd == 0x26:
                                self.frame_stats["frame_c"] += 1
                            elif cmd == 0x23:
                                self.frame_stats["mode_ack"] += 1
                            else:
                                self.frame_stats["unknown_navee"] += 1

                            if is_known:
                                # Known frames: log minimally (every 10th)
                                if self.frame_count % 10 == 0:
                                    self.log(f"  [{parsed['direction']}] {parsed['cmd_name']} "
                                             f"({len(frame_data)}B, chk={chk}) "
                                             f"[frame #{self.frame_count}]", console=True)
                            else:
                                # UNKNOWN frames: log EVERYTHING
                                self.log(f"*** UNKNOWN NAVEE FRAME ***", console=True)
                                self.log(f"  [{parsed['direction']}] CMD=0x{cmd:02X} "
                                         f"LEN={parsed['length']} ({len(frame_data)}B, chk={chk})",
                                         console=True)
                                self.log(f"  Hex: {self.hex_str(frame_data)}", console=True)

                            # Remove processed frame from buffer
                            self.buffer = self.buffer[j + 1:]
                            i = 0
                            break
                else:
                    # No footer found yet — might be incomplete, keep in buffer
                    if len(self.buffer) - i > 30:
                        # Too long without footer — probably not a valid frame
                        i += 1
                    else:
                        return  # Wait for more data

            # Check for standalone XMODEM bytes
            elif self.buffer[i] in XMODEM_NAMES:
                xmodem_name = XMODEM_NAMES[self.buffer[i]]
                self.frame_stats["xmodem"] += 1

                # Check for XMODEM block (SOH + seq + ~seq + 128 data + CRC)
                if self.buffer[i] == XMODEM_SOH and len(self.buffer) - i >= 133:
                    seq = self.buffer[i + 1]
                    seq_comp = self.buffer[i + 2]
                    block_data = bytes(self.buffer[i + 3:i + 131])
                    crc_hi = self.buffer[i + 131]
                    crc_lo = self.buffer[i + 132]
                    self.log(f"*** XMODEM BLOCK ***", console=True)
                    self.log(f"  SEQ={seq} ~SEQ={seq_comp} CRC={crc_hi:02X}{crc_lo:02X}",
                             console=True)
                    self.log(f"  Data[0:16]: {self.hex_str(block_data[:16])}", console=True)
                    self.log(f"  Data[-4:]:  {self.hex_str(block_data[-4:])}", console=True)
                    self.buffer = self.buffer[i + 133:]
                    i = 0
                    continue

                # Context: show surrounding bytes
                ctx_start = max(0, i - 4)
                ctx_end = min(len(self.buffer), i + 8)
                ctx = self.hex_str(self.buffer[ctx_start:ctx_end])
                self.log(f"*** {xmodem_name} *** at byte {self.byte_count - len(self.buffer) + i}",
                         console=True)
                self.log(f"  Context: {ctx}", console=True)
                i += 1

            else:
                i += 1

        # If buffer grows too large without being consumed, dump and clear
        if len(self.buffer) > 500:
            self.log(f"  [OVERFLOW] Buffer {len(self.buffer)} bytes, dumping...", console=True)
            # Show first/last bytes
            self.log(f"  First 32: {self.hex_str(self.buffer[:32])}", console=True)
            self.log(f"  Last 32:  {self.hex_str(self.buffer[-32:])}", console=True)
            self.frame_stats["raw_unknown"] += 1
            self.buffer.clear()

    def run(self, duration=None):
        """Main sniffing loop."""
        self.log_file = open(self.log_path, "w")

        self.log(f"UART BLDC DFU Sniffer", console=True)
        self.log(f"Port: {self.port}", console=True)
        self.log(f"Baud: {BAUD_RATE} 8N1", console=True)
        self.log(f"Log:  {self.log_path}", console=True)
        if duration:
            self.log(f"Duration: {duration}s (baseline mode)", console=True)
        self.log(f"{'=' * 60}", console=True)
        self.log(f"Listening... (Ctrl+C to stop)\n", console=True)

        try:
            ser = serial.Serial(self.port, BAUD_RATE, timeout=TIMEOUT,
                                bytesize=serial.EIGHTBITS,
                                parity=serial.PARITY_NONE,
                                stopbits=serial.STOPBITS_ONE)
        except Exception as e:
            self.log(f"ERROR: Cannot open {self.port}: {e}", console=True)
            return

        try:
            while self.running:
                if duration and self.elapsed() >= duration:
                    self.log(f"\nBaseline capture complete ({duration}s)", console=True)
                    break

                data = ser.read(256)
                if data:
                    self.byte_count += len(data)
                    self.buffer.extend(data)

                    # Log raw hex every second (summarized)
                    self.log(f"  +{len(data)} bytes (total: {self.byte_count})",
                             console=False)

                    self.process_buffer()

                # Periodic status
                if int(self.elapsed()) % 5 == 0 and int(self.elapsed()) > 0:
                    elapsed_int = int(self.elapsed())
                    if elapsed_int % 5 == 0 and self.byte_count > 0:
                        rate = self.byte_count / self.elapsed()
                        stats = ", ".join(f"{k}={v}" for k, v in self.frame_stats.items() if v > 0)
                        # Only log once per 5-second mark
                        pass

        except KeyboardInterrupt:
            self.log(f"\n\nStopped by user.", console=True)
        finally:
            ser.close()

            # Summary
            self.log(f"\n{'=' * 60}", console=True)
            self.log(f"CAPTURE SUMMARY", console=True)
            self.log(f"{'=' * 60}", console=True)
            self.log(f"Duration:    {self.elapsed():.1f}s", console=True)
            self.log(f"Total bytes: {self.byte_count}", console=True)
            self.log(f"Byte rate:   {self.byte_count / max(self.elapsed(), 0.1):.0f} B/s",
                     console=True)
            self.log(f"Frames:      {self.frame_count}", console=True)
            self.log(f"", console=True)
            self.log(f"Frame Statistics:", console=True)
            for k, v in self.frame_stats.items():
                if v > 0:
                    self.log(f"  {k:20s}: {v}", console=True)
            self.log(f"", console=True)

            if self.frame_stats["xmodem"] > 0:
                self.log(f"*** XMODEM ACTIVITY DETECTED! ***", console=True)
            if self.frame_stats["dfu_text"] > 0:
                self.log(f"*** DFU TEXT COMMANDS DETECTED! ***", console=True)
            if self.frame_stats["unknown_navee"] > 0:
                self.log(f"*** UNKNOWN NAVEE FRAMES DETECTED! ***", console=True)
            if self.frame_stats["xmodem"] == 0 and self.frame_stats["dfu_text"] == 0:
                self.log(f"No DFU/XMODEM activity detected on UART.", console=True)
                self.log(f"The dashboard may not relay BLDC DFU data via this UART line.",
                         console=True)

            self.log(f"\nLog saved: {self.log_path}", console=True)
            self.log_file.close()


def find_port():
    """Auto-detect CP2102 serial port."""
    patterns = [
        "/dev/tty.usbserial-*",
        "/dev/tty.SLAB_USBtoUART*",
        "/dev/ttyUSB*",
    ]
    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            return ports[0]
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Navee UART BLDC DFU Sniffer")
    parser.add_argument("port", nargs="?", help="Serial port (auto-detect if omitted)")
    parser.add_argument("--baseline", type=float, default=None,
                        help="Capture baseline for N seconds then stop")
    args = parser.parse_args()

    port = args.port or find_port()
    if not port:
        print("ERROR: No serial port found.")
        print("Available ports:")
        for pattern in ["/dev/tty.usbserial-*", "/dev/tty.SLAB_*", "/dev/ttyUSB*"]:
            for p in glob.glob(pattern):
                print(f"  {p}")
        print("\nUsage: python3 uart_bldc_sniffer.py /dev/tty.usbserial-XXXX")
        sys.exit(1)

    sniffer = UARTSniffer(port)

    # Handle Ctrl+C gracefully
    def sigint_handler(sig, frame):
        sniffer.running = False
    signal.signal(signal.SIGINT, sigint_handler)

    sniffer.run(duration=args.baseline)


if __name__ == "__main__":
    main()
