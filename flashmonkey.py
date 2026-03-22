#!/usr/bin/env python3
"""
FlashMonkey — Navee ST3 Pro Speed Unlock Tool

One-command speed unlock for Navee e-scooters.
Patches firmware, recalculates SHA-256, flashes via BLE OTA.

Usage:
    python3 flashmonkey.py scan                    Scan for Navee scooters
    python3 flashmonkey.py info                    Connect and show scooter info
    python3 flashmonkey.py patch firmware.bin      Patch a firmware file (offline)
    python3 flashmonkey.py unlock                  Full unlock: scan, patch, flash
    python3 flashmonkey.py unlock --key FM-XXXX-XXXX-XXXX-XXXX

(c) 2026 Martin Pfeffer | celox.io
"""

import argparse
import asyncio
import sys
from pathlib import Path

from core.patcher import parse_firmware, apply_speed_patch, FirmwareInfo, PatchResult
from core.license import validate_key_format, activate_license, Tier

BANNER = r"""
    _____ _           _     __  __             _
   |  ___| | __ _ ___| |__ |  \/  | ___  _ __ | | _____ _   _
   | |_  | |/ _` / __| '_ \| |\/| |/ _ \| '_ \| |/ / _ \ | | |
   |  _| | | (_| \__ \ | | | |  | | (_) | | | |   <  __/ |_| |
   |_|   |_|\__,_|___/_| |_|_|  |_|\___/|_| |_|_|\_\___|\__, |
                                                          |___/
   Navee ST3 Pro — Speed Unlock Tool
"""


def cmd_scan(args):
    """Scan for Navee scooters."""
    from core.scanner import scan_for_scooters

    print("Scanning for Navee scooters (10s)...")
    scooters = asyncio.run(scan_for_scooters(timeout=10.0))

    if not scooters:
        print("No scooters found. Make sure the scooter is ON and not connected to another app.")
        return 1

    print(f"\nFound {len(scooters)} scooter(s):\n")
    for i, s in enumerate(scooters):
        print(f"  [{i+1}] {s.name}")
        print(f"      Address: {s.address}")
        print(f"      RSSI:    {s.rssi} dBm")
        print(f"      Market:  {s.market}")
        print()
    return 0


def cmd_patch(args):
    """Patch a firmware file offline."""
    fw_path = Path(args.firmware)
    if not fw_path.exists():
        print(f"Error: File not found: {fw_path}")
        return 1

    fw_data = fw_path.read_bytes()

    # Parse firmware
    try:
        info = parse_firmware(fw_data)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Firmware: {fw_path.name}")
    print(f"  Model:      {info.model}")
    print(f"  Type:       0x{info.fw_type:02X} ({'Meter' if info.fw_type == 1 else 'Unknown'})")
    print(f"  Version:    {info.version}")
    print(f"  Image ID:   0x{info.image_id:04X} ({'App' if info.image_id == 0x2793 else '?'})")
    print(f"  Payload:    {info.payload_len} bytes")
    print(f"  SHA-256:    {'valid' if info.sha256_valid else 'INVALID!'}")

    if not info.sha256_valid:
        print("\nError: Original SHA-256 does not match. Firmware file may be corrupted.")
        return 1

    if info.crc16_field != 0:
        print(f"\nError: Firmware uses CRC-16 mode (0x{info.crc16_field:04X}), not SHA-256.")
        print("This firmware version is not supported.")
        return 1

    # Apply patch
    print("\nApplying speed unlock patch...")
    result = apply_speed_patch(fw_data)

    if not result.success:
        print(f"Error: {result.error}")
        return 1

    if result.old_bytes == result.new_bytes:
        print("Firmware is already patched!")
        return 0

    print(f"  Patch offset: 0x{result.patch_offset:04X}")
    print(f"  Old bytes:    {result.old_bytes.hex()} (BLS)")
    print(f"  New bytes:    {result.new_bytes.hex()} (NOP)")
    print(f"  Old SHA-256:  {result.old_sha256.hex()[:16]}...")
    print(f"  New SHA-256:  {result.new_sha256.hex()[:16]}...")

    # Save
    if args.output:
        out_path = Path(args.output)
    else:
        stem = fw_path.stem
        out_path = fw_path.parent / f"{stem}_UNLOCKED.bin"

    out_path.write_bytes(result.output_data)
    print(f"\nSaved: {out_path}")
    print(f"  Size: {len(result.output_data)} bytes")
    print(f"  Changes: 34 bytes (32 SHA-256 + 2 NOP)")

    print(f"\nFeatures unlocked:")
    print(f"  - Speed limit removed (set via BLE CMD 0x6E)")
    print(f"  - Zero start enabled (set via BLE, sys_stc[0x49]=1)")

    print(f"\nFlash with:")
    print(f"  python3 flashmonkey.py flash {out_path}")
    return 0


def cmd_unlock(args):
    """Full unlock workflow: scan, validate key, patch, flash."""
    # License check
    if args.key:
        if not validate_key_format(args.key):
            print(f"Error: Invalid key format. Expected: FM-XXXX-XXXX-XXXX-XXXX")
            return 1
        print(f"License key: {args.key}")
    else:
        print("No license key provided. Use --key FM-XXXX-XXXX-XXXX-XXXX")
        print("(For local testing, any correctly formatted key works)")
        return 1

    # Scan
    print("\nStep 1: Scanning for scooter...")
    from core.scanner import scan_for_scooters, HAS_BLEAK
    if not HAS_BLEAK:
        print("Error: bleak library required. Install with: pip3 install bleak")
        return 1

    scooters = asyncio.run(scan_for_scooters(timeout=10.0))
    if not scooters:
        print("No scooters found.")
        return 1

    scooter = scooters[0]
    print(f"  Found: {scooter.name} [{scooter.address}] ({scooter.market})")

    # Activate license
    print(f"\nStep 2: Activating license...")
    license_info = activate_license(args.key, scooter.address, scooter.name)
    if not license_info.valid:
        print(f"  Error: {license_info.error}")
        return 1
    print(f"  License valid! Tier: {license_info.tier.value}")
    print(f"  Features: {', '.join(license_info.features)}")

    # Patch firmware
    print(f"\nStep 3: Patching firmware...")
    if args.firmware:
        fw_path = Path(args.firmware)
    else:
        # Use bundled firmware
        fw_path = Path(__file__).parent.parent / "navee" / "tools" / "firmware" / "navee_meter_v2.0.3.1_ORIGINAL.bin"

    if not fw_path.exists():
        print(f"  Error: Firmware file not found: {fw_path}")
        print(f"  Provide firmware with: --firmware path/to/firmware.bin")
        return 1

    fw_data = fw_path.read_bytes()
    result = apply_speed_patch(fw_data)
    if not result.success:
        print(f"  Error: {result.error}")
        return 1
    print(f"  Patch applied at offset 0x{result.patch_offset:04X}")
    print(f"  SHA-256 recalculated")

    # Flash
    print(f"\nStep 4: Flashing firmware via BLE OTA...")
    print(f"  Target: {scooter.name} [{scooter.address}]")
    print(f"  Size: {len(result.output_data)} bytes ({len(result.output_data)//128} XMODEM blocks)")
    print()
    print("  [OTA flasher integration pending]")
    print("  For now, use the patched file directly:")
    print(f"  python3 navee/tools/ota_flasher.py <patched_firmware.bin>")

    return 0


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="FlashMonkey — Navee ST3 Pro Speed Unlock Tool",
        prog="flashmonkey",
    )
    sub = parser.add_subparsers(dest="command")

    # scan
    sub.add_parser("scan", help="Scan for Navee scooters")

    # patch
    p_patch = sub.add_parser("patch", help="Patch firmware file (offline)")
    p_patch.add_argument("firmware", help="Navee firmware binary (.bin)")
    p_patch.add_argument("-o", "--output", help="Output file path")

    # unlock
    p_unlock = sub.add_parser("unlock", help="Full unlock: scan, key, patch, flash")
    p_unlock.add_argument("--key", "-k", help="License key (FM-XXXX-XXXX-XXXX-XXXX)")
    p_unlock.add_argument("--firmware", "-f", help="Firmware file to patch")

    # flash
    p_flash = sub.add_parser("flash", help="Flash a pre-patched firmware via BLE OTA")
    p_flash.add_argument("firmware", help="Patched firmware binary")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "scan": cmd_scan,
        "patch": cmd_patch,
        "unlock": cmd_unlock,
    }

    if args.command in commands:
        return commands[args.command](args)
    else:
        print(f"Command '{args.command}' not yet implemented.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
