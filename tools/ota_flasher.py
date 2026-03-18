#!/usr/bin/env python3
"""
Navee ST3 Pro — BLE OTA Firmware Flasher

Flashes firmware binaries to the Navee ST3 Pro scooter over BLE using an
XMODEM-like protocol. Designed for macOS with the bleak library.

WARNING: Flashing custom firmware can BRICK your scooter permanently.
There is NO guaranteed recovery mechanism. Use at your own risk.

Usage:
    python3 ota_flasher.py firmware.bin                    # Flash firmware
    python3 ota_flasher.py firmware.bin --dry-run          # Simulate without sending
    python3 ota_flasher.py firmware.bin --backup-first     # Backup info before flash
    python3 ota_flasher.py --scan                          # Scan for scooters only
    python3 ota_flasher.py --read-info                     # Connect and read info only
    python3 ota_flasher.py firmware.bin --device-id AABBCCDDEEFF

Requires: pip3 install bleak
"""

import argparse
import asyncio
import hashlib
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError:
    print("ERROR: 'bleak' library required. Install with: pip3 install bleak")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "ota_flash_log.json"
CONFIG_FILE = SCRIPT_DIR / "ota_config.json"
BACKUP_DIR = SCRIPT_DIR / "firmware_backups"

# BLE UUIDs
SERVICE_UUID = "0000d0ff-3c17-d293-8e48-14fe2e4da212"
WRITE_UUID = "0000b002-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000b003-0000-1000-8000-00805f9b34fb"

# Frame constants
HEADER = bytes([0x55, 0xAA])
FOOTER = bytes([0xFE, 0xFD])

# Commands
CMD_AUTH = 0x30
CMD_AUTH_CHALLENGE = 0x31
CMD_POST_AUTH = 0x6F
CMD_VEHICLE_SETTINGS = 0x70
CMD_FIRMWARE_VERSION = 0x73
CMD_SERIAL_NUMBER = 0x74
CMD_BATTERY_SN = 0x75

# XMODEM constants
XMODEM_BLOCK_SIZE = 128
XMODEM_SOH = 0x01   # Start of Header (128-byte block)
XMODEM_EOT = 0x04   # End of Transmission
XMODEM_ACK = 0x06   # Acknowledge
XMODEM_NAK = 0x15   # Negative Acknowledge
XMODEM_CAN = 0x18   # Cancel
XMODEM_C = 0x43     # 'C' for CRC mode

# TODO: These OTA command bytes need to be confirmed through testing.
# They are approximate values based on APK analysis of f2/a.java.
# Candidates found in APK: 0x40-0x4F range, 0xF0-0xFF range.
CMD_OTA_START = 0x40       # TODO: Confirm - Enter OTA/DFU mode
CMD_OTA_HEADER = 0x41      # TODO: Confirm - Send firmware header info
CMD_OTA_DATA = 0x42        # TODO: Confirm - Send firmware data block
CMD_OTA_VERIFY = 0x43      # TODO: Confirm - Verify firmware integrity
CMD_OTA_REBOOT = 0x44      # TODO: Confirm - Reboot into new firmware
CMD_OTA_STATUS = 0x45      # TODO: Confirm - Query OTA status

# AES keys (from APK — all 5 work, index is arbitrary)
AUTH_KEY_INDEX = 1  # Use key "NaveeAUTHKEY002!"

# Scan name prefixes
SCOOTER_NAME_PREFIXES = ("NAVEE", "NV", "ST3")

# BLE MTU — macOS typically negotiates ~185, but we stay conservative
BLE_MTU = 20

# Timeouts
SCAN_TIMEOUT = 15.0
CONNECT_TIMEOUT = 20.0
RESPONSE_TIMEOUT = 5.0
OTA_BLOCK_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# CRC-16 (XMODEM / CCITT-FALSE)
# ---------------------------------------------------------------------------

def crc16_xmodem(data: bytes) -> int:
    """Calculate CRC-16/XMODEM (polynomial 0x1021, init 0x0000)."""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc

# ---------------------------------------------------------------------------
# Navee BLE Protocol Helpers
# ---------------------------------------------------------------------------

def build_frame(cmd: int, data: bytes = b"", flag: int = 0x00) -> bytes:
    """Build a Navee BLE protocol frame.

    Format: [55 AA] [flag] [cmd] [len] [data...] [checksum] [FE FD]
    Checksum: sum of all bytes from header through data, mod 256.
    """
    frame = bytearray()
    frame += HEADER
    frame.append(flag)
    frame.append(cmd)
    frame.append(len(data))
    frame += data
    checksum = sum(frame) % 256
    frame.append(checksum)
    frame += FOOTER
    return bytes(frame)


def parse_frame(raw: bytes) -> Optional[dict]:
    """Parse a Navee BLE protocol frame.

    Returns dict with 'flag', 'cmd', 'length', 'data', 'checksum' or None.
    """
    if len(raw) < 7:
        return None
    if raw[:2] != HEADER or raw[-2:] != FOOTER:
        return None
    flag = raw[2]
    cmd = raw[3]
    length = raw[4]
    data = raw[5:5 + length]
    checksum = raw[5 + length]
    expected = sum(raw[:5 + length]) % 256
    return {
        "flag": flag,
        "cmd": cmd,
        "length": length,
        "data": data,
        "checksum": checksum,
        "valid": checksum == expected,
    }


def hex_str(data: bytes) -> str:
    """Format bytes as hex string."""
    return " ".join(f"{b:02X}" for b in data)

# ---------------------------------------------------------------------------
# Firmware File Analysis
# ---------------------------------------------------------------------------

def analyze_firmware_file(filepath: Path) -> dict:
    """Analyze a Navee firmware binary and return metadata."""
    data = filepath.read_bytes()
    info = {
        "path": str(filepath),
        "filename": filepath.name,
        "size": len(data),
        "size_kb": round(len(data) / 1024, 1),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "crc16": crc16_xmodem(data),
        "blocks": (len(data) + XMODEM_BLOCK_SIZE - 1) // XMODEM_BLOCK_SIZE,
    }

    # Parse Navee firmware header
    if len(data) >= 16:
        try:
            info["model_string"] = data[:6].decode("latin-1").rstrip("\x00")
        except Exception:
            info["model_string"] = "unknown"

        info["type_byte"] = data[6] if len(data) > 6 else 0
        type_names = {0x01: "Meter (Dashboard)", 0x03: "BMS (Battery)"}
        info["type_name"] = type_names.get(info["type_byte"], f"Unknown (0x{info['type_byte']:02X})")

        try:
            info["version_string"] = data[7:15].decode("latin-1").rstrip("\x00")
        except Exception:
            info["version_string"] = "unknown"

        # Parse version string like "00030001" -> "2.0.3.1" (approximate)
        vs = info["version_string"]
        if len(vs) == 8 and vs.isdigit():
            info["version_readable"] = f"{int(vs[0:2])}.{int(vs[2:4])}.{int(vs[4:6])}.{int(vs[6:8])}"
        else:
            info["version_readable"] = vs

    # First 32 bytes hex dump for display
    info["header_hex"] = hex_str(data[:32])

    return info

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class FlashLog:
    """Structured logger for OTA flash operations."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries = []
        self.start_time = datetime.now()

    def log(self, event: str, **kwargs):
        entry = {
            "ts": datetime.now().isoformat(),
            "elapsed_s": round((datetime.now() - self.start_time).total_seconds(), 2),
            "event": event,
        }
        entry.update(kwargs)
        self.entries.append(entry)
        return entry

    def save(self):
        session = {
            "session_start": self.start_time.isoformat(),
            "session_end": datetime.now().isoformat(),
            "total_events": len(self.entries),
            "events": self.entries,
        }
        # Append to existing log or create new
        existing = []
        if self.log_path.exists():
            try:
                existing = json.loads(self.log_path.read_text())
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                existing = []
        existing.append(session)
        self.log_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

# ---------------------------------------------------------------------------
# Config (Device ID persistence)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config from ota_config.json."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(config: dict):
    """Save config to ota_config.json."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

# ---------------------------------------------------------------------------
# OTA Flasher
# ---------------------------------------------------------------------------

class NaveeOTAFlasher:
    """BLE OTA firmware flasher for Navee ST3 Pro."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.client: Optional[BleakClient] = None
        self.log = FlashLog(LOG_FILE)
        self.response_queue: asyncio.Queue = asyncio.Queue()
        self.authenticated = False
        self.firmware_version: Optional[str] = None
        self.serial_number: Optional[str] = None
        self.device_address: Optional[str] = None
        self._notification_buffer = bytearray()

    # --- BLE Notification Handler ---

    def _on_notify(self, char: BleakGATTCharacteristic, data: bytearray):
        """Handle incoming BLE notifications."""
        self._notification_buffer += data

        # Try to parse complete frames from the buffer
        while True:
            # Find header
            idx = self._notification_buffer.find(HEADER)
            if idx < 0:
                self._notification_buffer.clear()
                break
            if idx > 0:
                self._notification_buffer = self._notification_buffer[idx:]

            # Need at least 7 bytes for minimum frame
            if len(self._notification_buffer) < 7:
                break

            # Check if we have enough data
            length = self._notification_buffer[4]
            frame_len = 5 + length + 3  # header(2) + flag + cmd + len + data + checksum + footer(2)
            if len(self._notification_buffer) < frame_len:
                break

            frame_bytes = bytes(self._notification_buffer[:frame_len])
            self._notification_buffer = self._notification_buffer[frame_len:]

            parsed = parse_frame(frame_bytes)
            if parsed:
                self.log.log("ble_notify", cmd=f"0x{parsed['cmd']:02X}",
                             data=hex_str(parsed['data']), valid=parsed['valid'])
                asyncio.get_event_loop().call_soon_threadsafe(
                    self.response_queue.put_nowait, parsed
                )
            else:
                self.log.log("ble_notify_invalid", raw=hex_str(frame_bytes))

    # --- BLE Communication ---

    async def _write(self, data: bytes):
        """Write data to the BLE write characteristic."""
        if not self.client or not self.client.is_connected:
            raise ConnectionError("Not connected to scooter")
        self.log.log("ble_write", data=hex_str(data))
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)

    async def _send_cmd(self, cmd: int, data: bytes = b"") -> Optional[dict]:
        """Send a command and wait for the response."""
        frame = build_frame(cmd, data)
        # Drain any stale responses
        while not self.response_queue.empty():
            try:
                self.response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self._write(frame)

        # Wait for response with matching CMD
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                resp = await asyncio.wait_for(self.response_queue.get(), timeout=remaining)
                if resp["cmd"] == cmd:
                    return resp
                # Put back non-matching responses (telemetry etc.)
            except asyncio.TimeoutError:
                break
        return None

    async def _write_raw(self, data: bytes):
        """Write raw bytes (for XMODEM transfer, not wrapped in Navee frame)."""
        if self.dry_run:
            self.log.log("dry_run_raw_write", size=len(data))
            return
        await self._write(data)

    # --- Scanning ---

    async def scan(self, timeout: float = SCAN_TIMEOUT) -> list:
        """Scan for Navee scooters."""
        print(f"\nScanning for Navee scooters ({timeout}s)...")
        self.log.log("scan_start", timeout=timeout)

        found = []
        devices = await BleakScanner.discover(timeout=timeout)
        for d in devices:
            name = d.name or ""
            if any(name.upper().startswith(p) for p in SCOOTER_NAME_PREFIXES):
                found.append(d)
                rssi = getattr(d, 'rssi', None) or "?"
                print(f"  Found: {name} [{d.address}] RSSI={rssi}")
                self.log.log("scan_found", name=name, address=d.address)

        if not found:
            print("  No Navee scooters found.")
            print("  Tips: Make sure the scooter is ON and not connected to another app.")
        else:
            print(f"\n  {len(found)} scooter(s) found.")
        return found

    # --- Connection ---

    async def connect(self, address: str) -> bool:
        """Connect to a scooter by BLE address."""
        print(f"\nConnecting to {address}...")
        self.log.log("connect_start", address=address)

        try:
            self.client = BleakClient(address, timeout=CONNECT_TIMEOUT)
            await self.client.connect()
        except Exception as e:
            print(f"  Connection FAILED: {e}")
            self.log.log("connect_failed", error=str(e))
            return False

        if not self.client.is_connected:
            print("  Connection FAILED (not connected)")
            return False

        self.device_address = address
        print(f"  Connected!")
        self.log.log("connect_ok", address=address)

        # Subscribe to notifications
        try:
            await self.client.start_notify(NOTIFY_UUID, self._on_notify)
            print("  Notifications enabled.")
        except Exception as e:
            print(f"  WARNING: Could not enable notifications: {e}")
            self.log.log("notify_failed", error=str(e))

        return True

    async def disconnect(self):
        """Disconnect from the scooter."""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        print("  Disconnected.")

    # --- Authentication ---

    async def authenticate(self, device_id: bytes) -> bool:
        """Authenticate with the scooter using CMD 0x30.

        Args:
            device_id: 6-byte device ID (Navee account ID)
        """
        if len(device_id) != 6:
            print(f"  ERROR: Device ID must be 6 bytes, got {len(device_id)}")
            return False

        print(f"\nAuthenticating (Device ID: {hex_str(device_id)})...")
        self.log.log("auth_start", device_id=hex_str(device_id))

        # Build auth payload: [keyIndex, 0x00, deviceId[0..5], 0x00]
        auth_data = bytearray()
        auth_data.append(AUTH_KEY_INDEX)
        auth_data.append(0x00)
        auth_data += device_id
        auth_data.append(0x00)

        resp = await self._send_cmd(CMD_AUTH, bytes(auth_data))
        if resp is None:
            print("  Auth FAILED: No response")
            self.log.log("auth_failed", reason="no_response")
            return False

        if len(resp["data"]) > 0:
            status = resp["data"][0]
            if status == 0x00:
                print("  Authentication OK!")
                self.authenticated = True
                self.log.log("auth_ok")
                return True
            elif status == 0x02:
                print("  Auth FAILED: Unknown device (Device ID not registered)")
                self.log.log("auth_failed", reason="unknown_device", status=status)
                return False
            else:
                print(f"  Auth FAILED: Status 0x{status:02X}")
                self.log.log("auth_failed", reason="bad_status", status=status)
                return False

        print("  Auth FAILED: Empty response data")
        self.log.log("auth_failed", reason="empty_response")
        return False

    # --- Reading Scooter Info ---

    async def read_firmware_version(self) -> Optional[str]:
        """Read firmware version string from scooter (CMD 0x73)."""
        print("\nReading firmware version...")
        resp = await self._send_cmd(CMD_FIRMWARE_VERSION)
        if resp and resp["data"]:
            # data[0] is version/type byte, actual string starts at data[1]
            try:
                version = resp["data"][1:].decode("latin-1").rstrip("\x00")
            except Exception:
                version = hex_str(resp["data"])
            self.firmware_version = version
            print(f"  Firmware: {version}")
            self.log.log("firmware_version", version=version)
            return version
        print("  Could not read firmware version")
        return None

    async def read_serial_number(self) -> Optional[str]:
        """Read serial number from scooter (CMD 0x74)."""
        print("Reading serial number...")
        resp = await self._send_cmd(CMD_SERIAL_NUMBER)
        if resp and resp["data"]:
            try:
                serial = resp["data"][1:].decode("latin-1").rstrip("\x00")
            except Exception:
                serial = hex_str(resp["data"])
            self.serial_number = serial
            print(f"  Serial: {serial}")
            self.log.log("serial_number", serial=serial)
            return serial
        print("  Could not read serial number")
        return None

    async def read_vehicle_settings(self) -> Optional[dict]:
        """Read vehicle settings (CMD 0x70) and return parsed dict."""
        print("Reading vehicle settings...")
        resp = await self._send_cmd(CMD_VEHICLE_SETTINGS)
        if resp and resp["data"] and len(resp["data"]) >= 27:
            d = resp["data"]
            settings = {
                "drive_mode": "ECO" if d[2] == 0x03 else ("SPORT" if d[2] == 0x05 else f"0x{d[2]:02X}"),
                "lock_status": "LOCKED" if d[3] == 0x01 else "UNLOCKED",
                "cruise_control": bool(d[4]),
                "tail_light": bool(d[5]),
                "ers_level": d[6],
                "mileage_unit": "KM" if d[8] == 0x01 else "MPH",
                "auto_headlight": bool(d[9]),
                "tcs": bool(d[12]),
                "turn_sound": bool(d[13]),
                "max_speed_kmh": d[26],
            }
            for k, v in settings.items():
                print(f"  {k}: {v}")
            self.log.log("vehicle_settings", settings=settings)
            return settings
        print("  Could not read vehicle settings")
        return None

    async def read_all_info(self) -> dict:
        """Read all available scooter information."""
        info = {}
        info["firmware_version"] = await self.read_firmware_version()
        info["serial_number"] = await self.read_serial_number()
        info["settings"] = await self.read_vehicle_settings()
        return info

    # --- OTA Firmware Flash ---

    async def enter_ota_mode(self) -> bool:
        """Enter OTA/DFU mode on the scooter.

        TODO: The exact OTA entry command needs to be confirmed.
        Candidates from APK analysis (f2/a.java):
          - CMD 0x40 with specific payload
          - Possibly a command in 0xF0-0xFF range
          - Might require a specific data payload (e.g., firmware type byte)

        This is the first thing to test: send candidate commands and
        observe scooter behavior (screen changes, LED patterns, etc.)
        """
        print("\nEntering OTA mode...")
        self.log.log("ota_enter_start")

        if self.dry_run:
            print("  [DRY RUN] Would send OTA mode command")
            self.log.log("dry_run_ota_enter")
            return True

        # TODO: Try these commands in sequence during testing:
        # 1. CMD_OTA_START (0x40) with empty data
        # 2. CMD_OTA_START with firmware type byte [0x01] for Meter
        # 3. CMD_OTA_START with firmware size as 4-byte LE
        # 4. Check 0xF0-0xFF range commands
        #
        # Test procedure:
        #   - Connect + auth
        #   - Send candidate command
        #   - Observe: does the scooter screen change? Does it enter a special mode?
        #   - Check response for ACK/NAK

        # Attempt: CMD 0x40 with firmware type indicator
        resp = await self._send_cmd(CMD_OTA_START, bytes([0x01]))  # 0x01 = Meter type
        if resp:
            status = resp["data"][0] if resp["data"] else 0xFF
            if status == 0x00:
                print("  OTA mode entered!")
                self.log.log("ota_enter_ok")
                return True
            else:
                print(f"  OTA mode response: 0x{status:02X}")
                self.log.log("ota_enter_response", status=f"0x{status:02X}",
                             data=hex_str(resp["data"]))
                # Even non-zero might indicate OTA mode on some firmware versions
                # TODO: Interpret response codes
                return False
        else:
            print("  WARNING: No response to OTA mode command")
            self.log.log("ota_enter_no_response")
            # The scooter might have entered OTA mode silently
            # TODO: Check if BLE connection is still alive
            return False

    async def send_firmware_header(self, fw_info: dict) -> bool:
        """Send firmware header information to scooter before data transfer.

        TODO: The exact header format needs to be confirmed.
        From APK analysis, the firmware file starts with a header containing:
          - Model string (6 bytes, e.g., "T22020")
          - Type byte (1 byte, 0x01=Meter)
          - Version string (8 bytes)
        This header might need to be sent as a separate command.
        """
        print("\nSending firmware header info...")
        self.log.log("ota_header_start", fw_info={k: v for k, v in fw_info.items()
                                                   if k in ("filename", "size", "type_byte",
                                                            "version_string", "crc16")})

        if self.dry_run:
            print("  [DRY RUN] Would send firmware header")
            return True

        # TODO: Build header payload. Possible formats:
        # Option A: Send the first N bytes of the firmware file as-is
        # Option B: Send a structured payload with size + CRC + version info
        # Option C: The header is part of the XMODEM data stream (no separate command)

        # Attempt: Send type + version + size + CRC as header
        header_data = bytearray()
        header_data.append(fw_info.get("type_byte", 0x01))
        # Firmware size as 4-byte LE
        header_data += struct.pack("<I", fw_info["size"])
        # CRC-16 as 2-byte LE
        header_data += struct.pack("<H", fw_info["crc16"])

        resp = await self._send_cmd(CMD_OTA_HEADER, bytes(header_data))
        if resp:
            status = resp["data"][0] if resp["data"] else 0xFF
            print(f"  Header response: 0x{status:02X}")
            self.log.log("ota_header_response", status=f"0x{status:02X}")
            return status == 0x00
        else:
            print("  WARNING: No response to header command")
            self.log.log("ota_header_no_response")
            return False

    async def flash_firmware(self, firmware_path: Path, fw_info: dict) -> bool:
        """Flash firmware using XMODEM-like block transfer.

        The XMODEM transfer sends 128-byte blocks with:
          - SOH (0x01) — start of block
          - Block number (1 byte, wraps at 255)
          - Complement of block number (255 - block_num)
          - 128 bytes of data (padded with 0xFF if last block is short)
          - CRC-16 (2 bytes, big-endian)

        TODO: Confirm whether the XMODEM data is:
          (a) Sent raw over the BLE write characteristic, OR
          (b) Wrapped in Navee frames (CMD 0x42), OR
          (c) Uses a completely different framing
        The APK's f2/a.java should clarify this.
        """
        fw_data = firmware_path.read_bytes()
        total_blocks = fw_info["blocks"]

        print(f"\n{'='*60}")
        print(f"  FIRMWARE FLASH")
        print(f"{'='*60}")
        print(f"  File:     {fw_info['filename']}")
        print(f"  Size:     {fw_info['size']} bytes ({fw_info['size_kb']} KB)")
        print(f"  Type:     {fw_info.get('type_name', 'unknown')}")
        print(f"  Version:  {fw_info.get('version_readable', 'unknown')}")
        print(f"  CRC-16:   0x{fw_info['crc16']:04X}")
        print(f"  MD5:      {fw_info['md5']}")
        print(f"  SHA-256:  {fw_info['sha256']}")
        print(f"  Blocks:   {total_blocks} x {XMODEM_BLOCK_SIZE} bytes")
        if self.dry_run:
            print(f"  Mode:     *** DRY RUN — no data will be sent ***")
        print(f"{'='*60}")

        self.log.log("flash_start", blocks=total_blocks, size=fw_info["size"],
                     dry_run=self.dry_run)

        # --- Send blocks ---
        successful_blocks = 0
        failed_blocks = 0
        start_time = time.monotonic()

        for block_num in range(1, total_blocks + 1):
            offset = (block_num - 1) * XMODEM_BLOCK_SIZE
            block_data = fw_data[offset:offset + XMODEM_BLOCK_SIZE]

            # Pad last block with 0xFF
            if len(block_data) < XMODEM_BLOCK_SIZE:
                block_data += bytes([0xFF] * (XMODEM_BLOCK_SIZE - len(block_data)))

            # Build XMODEM block
            seq = block_num & 0xFF  # Wraps at 255
            seq_comp = 0xFF - seq
            crc = crc16_xmodem(block_data)

            xmodem_block = bytearray()
            xmodem_block.append(XMODEM_SOH)
            xmodem_block.append(seq)
            xmodem_block.append(seq_comp)
            xmodem_block += block_data
            xmodem_block += struct.pack(">H", crc)  # CRC big-endian

            # Progress
            pct = (block_num / total_blocks) * 100
            elapsed = time.monotonic() - start_time
            if block_num > 1 and elapsed > 0:
                rate = (block_num - 1) / elapsed
                remaining = (total_blocks - block_num) / rate if rate > 0 else 0
                eta_str = f" ETA {remaining:.0f}s"
            else:
                eta_str = ""

            bar_width = 30
            filled = int(bar_width * block_num / total_blocks)
            bar = "#" * filled + "-" * (bar_width - filled)
            print(f"\r  [{bar}] {pct:5.1f}% Block {block_num}/{total_blocks}{eta_str}   ",
                  end="", flush=True)

            if self.dry_run:
                self.log.log("dry_run_block", block=block_num, crc=f"0x{crc:04X}")
                successful_blocks += 1
                # Simulate transfer delay
                await asyncio.sleep(0.01)
                continue

            # TODO: Determine the correct sending method:
            #
            # Method A: Raw XMODEM over BLE characteristic
            #   - Split xmodem_block into BLE_MTU-sized chunks
            #   - Write each chunk sequentially
            #   - Wait for ACK after the full block
            #
            # Method B: Wrapped in Navee frame
            #   - Use CMD_OTA_DATA with xmodem_block as data
            #   - Navee framing adds header/footer/checksum
            #
            # Method C: Just the data, no XMODEM framing
            #   - Send 128-byte blocks wrapped in Navee CMD frames
            #   - CRC sent separately or as part of data field
            #
            # Starting with Method A (raw XMODEM):

            # Split into BLE-MTU-sized chunks and write
            retries = 3
            block_ok = False
            for attempt in range(retries):
                try:
                    # Send XMODEM block in chunks
                    chunk_size = BLE_MTU
                    for i in range(0, len(xmodem_block), chunk_size):
                        chunk = bytes(xmodem_block[i:i + chunk_size])
                        await self.client.write_gatt_char(WRITE_UUID, chunk, response=False)
                        await asyncio.sleep(0.005)  # Small inter-chunk delay

                    # Wait for ACK/NAK
                    try:
                        resp = await asyncio.wait_for(
                            self.response_queue.get(), timeout=OTA_BLOCK_TIMEOUT
                        )
                        # Check for XMODEM ACK
                        if resp.get("cmd") == CMD_OTA_DATA:
                            resp_data = resp.get("data", b"")
                            if resp_data and resp_data[0] == XMODEM_ACK:
                                block_ok = True
                                break
                            elif resp_data and resp_data[0] == XMODEM_NAK:
                                self.log.log("block_nak", block=block_num, attempt=attempt)
                                continue
                            elif resp_data and resp_data[0] == XMODEM_CAN:
                                print(f"\n\n  ABORT: Scooter cancelled transfer at block {block_num}!")
                                self.log.log("transfer_cancelled", block=block_num)
                                return False
                        # Also check for raw ACK byte in notification
                        # TODO: The ACK might come as a single raw byte, not a Navee frame
                        block_ok = True  # Assume OK if we got any response
                        break
                    except asyncio.TimeoutError:
                        self.log.log("block_timeout", block=block_num, attempt=attempt)
                        # Some implementations don't ACK every block
                        # TODO: Determine if ACK is expected per-block or per-batch
                        block_ok = True  # Optimistic: continue if no NAK
                        break

                except Exception as e:
                    self.log.log("block_error", block=block_num, attempt=attempt, error=str(e))
                    if attempt < retries - 1:
                        await asyncio.sleep(0.5)

            if block_ok:
                successful_blocks += 1
            else:
                failed_blocks += 1
                print(f"\n  WARNING: Block {block_num} failed after {retries} attempts!")
                self.log.log("block_failed", block=block_num)
                if failed_blocks >= 5:
                    print(f"\n  ABORT: Too many failed blocks ({failed_blocks}). Stopping transfer.")
                    self.log.log("transfer_aborted", reason="too_many_failures",
                                 failed=failed_blocks, successful=successful_blocks)
                    return False

        # End of transmission
        print()  # Newline after progress bar

        elapsed = time.monotonic() - start_time
        rate = fw_info["size"] / elapsed if elapsed > 0 else 0

        print(f"\n  Transfer complete:")
        print(f"    Blocks sent:   {successful_blocks}/{total_blocks}")
        print(f"    Blocks failed: {failed_blocks}")
        print(f"    Time:          {elapsed:.1f}s")
        print(f"    Rate:          {rate:.0f} bytes/s")

        self.log.log("transfer_complete", successful=successful_blocks,
                     failed=failed_blocks, total=total_blocks,
                     elapsed_s=round(elapsed, 1), rate_bps=round(rate, 0))

        if not self.dry_run:
            # Send EOT
            print("  Sending EOT (End of Transmission)...")
            # TODO: EOT might be raw byte or wrapped in Navee frame
            eot_frame = build_frame(CMD_OTA_DATA, bytes([XMODEM_EOT]))
            await self._write(eot_frame)
            await asyncio.sleep(1.0)

        return failed_blocks == 0

    async def verify_firmware(self, expected_version: str) -> bool:
        """Verify firmware after flash by reading version.

        TODO: There might be a specific OTA verification command that
        triggers integrity checking on the scooter side.
        """
        print("\nVerifying firmware...")
        self.log.log("verify_start", expected=expected_version)

        if self.dry_run:
            print("  [DRY RUN] Would verify firmware version")
            return True

        # TODO: Send verification command if one exists
        # resp = await self._send_cmd(CMD_OTA_VERIFY)

        # Wait for scooter to potentially reboot
        print("  Waiting for scooter to apply firmware (10s)...")
        await asyncio.sleep(10.0)

        # Try to read firmware version
        version = await self.read_firmware_version()
        if version:
            if expected_version in version:
                print(f"  Verification OK: {version}")
                self.log.log("verify_ok", version=version)
                return True
            else:
                print(f"  WARNING: Version mismatch!")
                print(f"    Expected: {expected_version}")
                print(f"    Got:      {version}")
                self.log.log("verify_mismatch", expected=expected_version, got=version)
                return False
        else:
            print("  WARNING: Could not read firmware version after flash")
            print("  The scooter may need to be power-cycled.")
            self.log.log("verify_failed", reason="no_version")
            return False

    # --- Main Flash Orchestration ---

    async def run_flash(self, firmware_path: Path, device_id: bytes,
                        address: Optional[str] = None, backup_first: bool = False):
        """Full OTA flash workflow."""

        print("\n" + "=" * 60)
        print("  NAVEE ST3 PRO — OTA FIRMWARE FLASHER")
        if self.dry_run:
            print("  *** DRY RUN MODE — NO FIRMWARE WILL BE WRITTEN ***")
        print("=" * 60)

        print("""
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  !!                                                       !!
  !!  WARNING: FLASHING FIRMWARE CAN BRICK YOUR SCOOTER!   !!
  !!                                                       !!
  !!  - There is NO guaranteed recovery mechanism          !!
  !!  - A failed flash may leave the scooter inoperable    !!
  !!  - The OTA protocol details are APPROXIMATE           !!
  !!  - This tool has NOT been fully validated              !!
  !!                                                       !!
  !!  PROCEED AT YOUR OWN RISK!                            !!
  !!                                                       !!
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
""")

        # --- Step 0: Analyze firmware file ---
        print("[Step 0] Analyzing firmware file...")
        if not firmware_path.exists():
            print(f"  ERROR: Firmware file not found: {firmware_path}")
            return False

        fw_info = analyze_firmware_file(firmware_path)
        print(f"  File:     {fw_info['filename']}")
        print(f"  Size:     {fw_info['size']} bytes ({fw_info['size_kb']} KB)")
        print(f"  Type:     {fw_info.get('type_name', 'unknown')}")
        print(f"  Version:  {fw_info.get('version_readable', 'unknown')}")
        print(f"  Header:   {fw_info.get('model_string', '?')}")
        print(f"  CRC-16:   0x{fw_info['crc16']:04X}")
        print(f"  SHA-256:  {fw_info['sha256']}")
        print(f"  Blocks:   {fw_info['blocks']}")
        self.log.log("firmware_analyzed", **{k: v for k, v in fw_info.items()
                                              if k != "header_hex"})

        # Basic sanity checks on firmware file
        if fw_info["size"] < 1024:
            print("  ERROR: Firmware file too small (< 1 KB). Probably not valid.")
            return False
        if fw_info["size"] > 512 * 1024:
            print("  ERROR: Firmware file too large (> 512 KB). Probably not valid.")
            return False
        if fw_info.get("model_string", "")[:1] != "T":
            print(f"  WARNING: Firmware header does not start with 'T' (got '{fw_info.get('model_string', '')}')")
            print("  This may not be a valid Navee firmware file!")
            resp = input("  Continue anyway? (y/N): ").strip().lower()
            if resp != "y":
                print("  Aborted.")
                return False

        # --- Step 1: Scan and connect ---
        print("\n[Step 1] Connecting to scooter...")
        if not address:
            scooters = await self.scan()
            if not scooters:
                print("  No scooters found. Aborting.")
                return False
            if len(scooters) == 1:
                address = scooters[0].address
                print(f"  Auto-selecting: {scooters[0].name} [{address}]")
            else:
                print("\n  Multiple scooters found. Select one:")
                for i, s in enumerate(scooters):
                    print(f"    {i+1}. {s.name} [{s.address}]")
                try:
                    choice = int(input("  Enter number: ").strip()) - 1
                    address = scooters[choice].address
                except (ValueError, IndexError):
                    print("  Invalid selection. Aborting.")
                    return False

        if not await self.connect(address):
            return False

        try:
            # --- Step 2: Authenticate ---
            print("\n[Step 2] Authenticating...")
            if not await self.authenticate(device_id):
                print("  Authentication failed. Aborting.")
                return False

            # Small delay after auth for telemetry to start
            await asyncio.sleep(1.0)

            # --- Step 3: Read current info ---
            print("\n[Step 3] Reading scooter info...")
            scooter_info = await self.read_all_info()

            # --- Step 3b: Backup ---
            if backup_first:
                print("\n[Step 3b] Backing up current firmware info...")
                BACKUP_DIR.mkdir(exist_ok=True)
                backup_data = {
                    "timestamp": datetime.now().isoformat(),
                    "address": address,
                    "firmware_version": scooter_info.get("firmware_version"),
                    "serial_number": scooter_info.get("serial_number"),
                    "settings": scooter_info.get("settings"),
                    "device_id": hex_str(device_id),
                }
                backup_path = BACKUP_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                backup_path.write_text(json.dumps(backup_data, indent=2))
                print(f"  Backup saved: {backup_path}")
                self.log.log("backup_saved", path=str(backup_path))

            # --- Step 4: Confirmation ---
            print(f"\n{'='*60}")
            print("  FLASH CONFIRMATION")
            print(f"{'='*60}")
            print(f"  Current firmware:  {scooter_info.get('firmware_version', 'unknown')}")
            print(f"  New firmware:      {fw_info.get('version_readable', 'unknown')}")
            print(f"  Firmware type:     {fw_info.get('type_name', 'unknown')}")
            print(f"  File:              {fw_info['filename']}")
            print(f"  Size:              {fw_info['size']} bytes")
            print(f"  CRC-16:            0x{fw_info['crc16']:04X}")
            if self.dry_run:
                print(f"  Mode:              *** DRY RUN ***")
            print(f"{'='*60}")

            if not self.dry_run:
                print("\n  To proceed, type YES (in capitals) and press Enter.")
                print("  Anything else will abort.")
                confirm = input("  > ").strip()
                if confirm != "YES":
                    print("  Flash ABORTED by user.")
                    self.log.log("flash_aborted", reason="user_cancelled")
                    return False
            else:
                print("\n  [DRY RUN] Skipping confirmation prompt")

            # --- Step 5: Enter OTA mode ---
            print("\n[Step 5] Entering OTA mode...")
            ota_ok = await self.enter_ota_mode()
            if not ota_ok:
                print("  WARNING: OTA mode entry may have failed.")
                if not self.dry_run:
                    resp = input("  Continue anyway? (y/N): ").strip().lower()
                    if resp != "y":
                        print("  Aborted.")
                        return False

            # --- Step 6: Send firmware header ---
            print("\n[Step 6] Sending firmware header...")
            header_ok = await self.send_firmware_header(fw_info)
            if not header_ok and not self.dry_run:
                print("  WARNING: Firmware header may not have been accepted.")
                resp = input("  Continue anyway? (y/N): ").strip().lower()
                if resp != "y":
                    print("  Aborted.")
                    return False

            # --- Step 7: Flash firmware ---
            print("\n[Step 7] Flashing firmware...")
            flash_ok = await self.flash_firmware(firmware_path, fw_info)
            if not flash_ok:
                print("\n  FLASH FAILED!")
                self.log.log("flash_failed")
                return False

            # --- Step 8: Verify ---
            print("\n[Step 8] Verifying...")
            expected_ver = fw_info.get("version_readable", "")
            verify_ok = await self.verify_firmware(expected_ver)

            # --- Done ---
            print(f"\n{'='*60}")
            if flash_ok and (verify_ok or self.dry_run):
                print("  FLASH COMPLETE!")
                self.log.log("flash_complete", verified=verify_ok)
            else:
                print("  FLASH COMPLETED WITH WARNINGS")
                print("  Please power-cycle the scooter and verify operation.")
                self.log.log("flash_complete_warnings")
            print(f"{'='*60}")

            return flash_ok

        finally:
            await self.disconnect()
            self.log.save()
            print(f"\n  Log saved: {LOG_FILE}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_device_id(id_str: str) -> bytes:
    """Parse device ID from hex string (with or without separators)."""
    clean = id_str.replace(":", "").replace("-", "").replace(" ", "").strip()
    if len(clean) != 12:
        raise ValueError(f"Device ID must be 6 bytes (12 hex chars), got {len(clean)} chars: '{clean}'")
    return bytes.fromhex(clean)


async def main_async():
    parser = argparse.ArgumentParser(
        description="Navee ST3 Pro BLE OTA Firmware Flasher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --scan                                  Scan for scooters
  %(prog)s --read-info --device-id AABBCCDDEEFF    Connect and read info
  %(prog)s firmware.bin --dry-run                   Simulate flash
  %(prog)s firmware.bin --device-id AABBCCDDEEFF    Flash firmware
  %(prog)s firmware.bin --backup-first              Backup info then flash

Staged testing (recommended order):
  1. %(prog)s --scan
  2. %(prog)s --read-info --device-id <ID>
  3. %(prog)s firmware.bin --dry-run --device-id <ID>
  4. %(prog)s firmware.bin --device-id <ID>

WARNING: Flashing firmware can permanently brick your scooter!
        """
    )
    parser.add_argument("firmware", nargs="?", help="Path to firmware binary (.bin)")
    parser.add_argument("--scan", action="store_true", help="Scan for scooters and exit")
    parser.add_argument("--read-info", action="store_true",
                        help="Connect, authenticate, read info, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate everything without sending firmware data")
    parser.add_argument("--backup-first", action="store_true",
                        help="Save current firmware info before flashing")
    parser.add_argument("--device-id", type=str, default=None,
                        help="6-byte device ID as hex (e.g., AABBCCDDEEFF)")
    parser.add_argument("--address", type=str, default=None,
                        help="BLE MAC address to connect to directly (skip scan)")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze firmware file and exit (no BLE needed)")

    args = parser.parse_args()

    # --- Analyze-only mode ---
    if args.analyze:
        if not args.firmware:
            print("ERROR: Firmware file path required with --analyze")
            sys.exit(1)
        fw_path = Path(args.firmware)
        if not fw_path.exists():
            print(f"ERROR: File not found: {fw_path}")
            sys.exit(1)
        info = analyze_firmware_file(fw_path)
        print(f"\nFirmware Analysis: {info['filename']}")
        print(f"  Size:      {info['size']} bytes ({info['size_kb']} KB)")
        print(f"  Model:     {info.get('model_string', '?')}")
        print(f"  Type:      {info.get('type_name', '?')}")
        print(f"  Version:   {info.get('version_readable', '?')}")
        print(f"  CRC-16:    0x{info['crc16']:04X}")
        print(f"  MD5:       {info['md5']}")
        print(f"  SHA-256:   {info['sha256']}")
        print(f"  Blocks:    {info['blocks']} x {XMODEM_BLOCK_SIZE} bytes")
        print(f"  Header:    {info['header_hex']}")
        return

    # --- Scan-only mode ---
    if args.scan:
        flasher = NaveeOTAFlasher()
        await flasher.scan()
        return

    # --- Load / prompt for device ID ---
    config = load_config()
    device_id = None

    if args.device_id:
        try:
            device_id = parse_device_id(args.device_id)
            config["device_id"] = args.device_id.replace(":", "").replace("-", "").replace(" ", "")
            save_config(config)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    elif config.get("device_id"):
        try:
            device_id = parse_device_id(config["device_id"])
            print(f"Using saved Device ID: {config['device_id']}")
        except ValueError:
            pass

    if device_id is None and (args.read_info or args.firmware):
        print("\nDevice ID required for authentication.")
        print("The Device ID is your 6-byte Navee Account ID (from BT-HCI capture).")
        print("Format: 12 hex characters, e.g., AABBCCDDEEFF")
        id_str = input("Device ID: ").strip()
        if not id_str:
            print("ERROR: Device ID is required")
            sys.exit(1)
        try:
            device_id = parse_device_id(id_str)
            config["device_id"] = id_str.replace(":", "").replace("-", "").replace(" ", "")
            save_config(config)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    # --- Read-info mode ---
    if args.read_info:
        flasher = NaveeOTAFlasher()
        flasher.log.log("session_start", mode="read_info")

        address = args.address
        if not address:
            scooters = await flasher.scan()
            if not scooters:
                print("No scooters found.")
                return
            address = scooters[0].address
            print(f"Auto-selecting: {scooters[0].name} [{address}]")

        if not await flasher.connect(address):
            return

        try:
            if await flasher.authenticate(device_id):
                await asyncio.sleep(1.0)
                await flasher.read_all_info()
            else:
                print("Authentication failed.")
        finally:
            await flasher.disconnect()
            flasher.log.save()
            print(f"\nLog saved: {LOG_FILE}")
        return

    # --- Flash mode ---
    if args.firmware:
        fw_path = Path(args.firmware)
        if not fw_path.exists():
            print(f"ERROR: Firmware file not found: {fw_path}")
            sys.exit(1)

        flasher = NaveeOTAFlasher(dry_run=args.dry_run)
        flasher.log.log("session_start", mode="flash", dry_run=args.dry_run,
                        firmware=str(fw_path))

        await flasher.run_flash(
            firmware_path=fw_path,
            device_id=device_id,
            address=args.address,
            backup_first=args.backup_first,
        )
        return

    # No action specified
    parser.print_help()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
