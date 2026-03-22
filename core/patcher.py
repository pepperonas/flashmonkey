"""
FlashMonkey Patch Engine — patches Navee firmware and recalculates SHA-256.

Supports:
- Speed unlock (BLS -> NOP at lift_speed_limit check)
- Zero start (enabled automatically by speed patch, configured via BLE)
- Any Navee meter firmware version (pattern-based patch detection)

(c) 2026 Martin Pfeffer | celox.io
"""

import hashlib
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PatchType(Enum):
    SPEED_UNLOCK = "speed_unlock"
    # Future patches can be added here


@dataclass
class FirmwareInfo:
    """Parsed firmware metadata."""
    model: str              # e.g. "T2202"
    fw_type: int            # 0x01 = Meter
    version: str            # e.g. "00030001"
    ic_type: int            # 0x05 for RTL8762C
    image_id: int           # 0x2793 = App
    crc16_field: int        # 0x0000 = SHA-256 mode
    payload_len: int        # Payload size in bytes
    sha256_stored: bytes    # 32 bytes SHA-256 from header
    sha256_valid: bool      # Whether stored SHA matches computed
    file_size: int          # Total file size


@dataclass
class PatchResult:
    """Result of a patch operation."""
    success: bool
    patch_type: PatchType
    patch_offset: int           # Offset in firmware file
    old_bytes: bytes            # Original bytes
    new_bytes: bytes            # Patched bytes
    old_sha256: bytes           # Original SHA-256
    new_sha256: bytes           # New SHA-256
    output_data: Optional[bytes] = None  # Patched firmware binary
    error: Optional[str] = None


# RTL8762C Image Header constants
IMG_HEADER_OFFSET = 0x400
IMG_HEADER_SIZE = 1024
DFU_HEADER_SIZE = 12
SHA256_OFFSET = 372
SHA256_SIZE = 32

# Speed limit patch
SPEED_PATCH_CONTEXT = bytes([
    0x0E, 0x2D, 0x02, 0xD8, 0x04, 0xE0, 0x0A, 0x2D, 0x02, 0xD9
])
SPEED_PATCH_OFFSET_IN_CONTEXT = 8
SPEED_PATCH_OLD = bytes([0x02, 0xD9])  # BLS
SPEED_PATCH_NEW = bytes([0x00, 0xBF])  # NOP


def compute_sha256(data: bytes, img_off: int, payload_len: int) -> bytes:
    """Compute SHA-256 over the 3 RTL8762C SDK-defined regions.

    Regions (from Realtek Bee2 SDK, slient_dfu_check_sha256):
      1: header[12:372]             (360 bytes)
      2: header[404:752]            (348 bytes)
      3: header[1008:1024]+payload  (16 + payload_len bytes)
    """
    r1 = data[img_off + DFU_HEADER_SIZE : img_off + SHA256_OFFSET]
    r2 = data[img_off + SHA256_OFFSET + SHA256_SIZE : img_off + 752]
    r3 = data[img_off + IMG_HEADER_SIZE - 16 : img_off + IMG_HEADER_SIZE + payload_len]

    return hashlib.sha256(r1 + r2 + r3).digest()


def parse_firmware(data: bytes) -> FirmwareInfo:
    """Parse and validate a Navee OTA firmware binary."""
    if len(data) < IMG_HEADER_OFFSET + IMG_HEADER_SIZE:
        raise ValueError(f"File too small ({len(data)} bytes)")

    # Navee OTA header (first 0x400 bytes)
    model = data[:5].decode('ascii', errors='replace').rstrip('\x00')
    fw_type = data[6]
    version = data[7:15].decode('ascii', errors='replace').rstrip('\x00')

    # RTL8762C image header (at offset 0x400)
    img_off = IMG_HEADER_OFFSET
    ic_type = data[img_off]
    image_id = struct.unpack('<H', data[img_off + 4 : img_off + 6])[0]
    crc16_field = struct.unpack('<H', data[img_off + 6 : img_off + 8])[0]
    payload_len = struct.unpack('<I', data[img_off + 8 : img_off + 12])[0]
    sha256_stored = data[img_off + SHA256_OFFSET : img_off + SHA256_OFFSET + SHA256_SIZE]

    # Verify SHA-256
    sha256_computed = compute_sha256(data, img_off, payload_len)
    sha256_valid = sha256_computed == sha256_stored

    return FirmwareInfo(
        model=model,
        fw_type=fw_type,
        version=version,
        ic_type=ic_type,
        image_id=image_id,
        crc16_field=crc16_field,
        payload_len=payload_len,
        sha256_stored=sha256_stored,
        sha256_valid=sha256_valid,
        file_size=len(data),
    )


def find_speed_patch_offset(data: bytes) -> int:
    """Find the BLS instruction to patch by surrounding byte context."""
    idx = data.find(SPEED_PATCH_CONTEXT)
    if idx < 0:
        return -1
    return idx + SPEED_PATCH_OFFSET_IN_CONTEXT


def apply_speed_patch(data: bytes) -> PatchResult:
    """Apply speed unlock patch and recalculate SHA-256."""
    img_off = IMG_HEADER_OFFSET

    # Find patch location
    patch_off = find_speed_patch_offset(data)
    if patch_off < 0:
        return PatchResult(
            success=False, patch_type=PatchType.SPEED_UNLOCK,
            patch_offset=-1, old_bytes=b'', new_bytes=b'',
            old_sha256=b'', new_sha256=b'',
            error="Patch pattern not found in firmware"
        )

    old_bytes = data[patch_off:patch_off + 2]

    # Already patched?
    if old_bytes == SPEED_PATCH_NEW:
        return PatchResult(
            success=True, patch_type=PatchType.SPEED_UNLOCK,
            patch_offset=patch_off, old_bytes=old_bytes, new_bytes=old_bytes,
            old_sha256=data[img_off + SHA256_OFFSET : img_off + SHA256_OFFSET + SHA256_SIZE],
            new_sha256=data[img_off + SHA256_OFFSET : img_off + SHA256_OFFSET + SHA256_SIZE],
            output_data=data,
        )

    if old_bytes != SPEED_PATCH_OLD:
        return PatchResult(
            success=False, patch_type=PatchType.SPEED_UNLOCK,
            patch_offset=patch_off, old_bytes=old_bytes, new_bytes=b'',
            old_sha256=b'', new_sha256=b'',
            error=f"Unexpected bytes at patch offset: {old_bytes.hex()} (expected {SPEED_PATCH_OLD.hex()})"
        )

    # Get original SHA
    payload_len = struct.unpack('<I', data[img_off + 8 : img_off + 12])[0]
    old_sha = data[img_off + SHA256_OFFSET : img_off + SHA256_OFFSET + SHA256_SIZE]

    # Apply patch
    patched = bytearray(data)
    patched[patch_off] = SPEED_PATCH_NEW[0]
    patched[patch_off + 1] = SPEED_PATCH_NEW[1]

    # Recalculate SHA-256
    new_sha = compute_sha256(bytes(patched), img_off, payload_len)
    patched[img_off + SHA256_OFFSET : img_off + SHA256_OFFSET + SHA256_SIZE] = new_sha

    # Verify
    verify_sha = compute_sha256(bytes(patched), img_off, payload_len)
    if verify_sha != new_sha:
        return PatchResult(
            success=False, patch_type=PatchType.SPEED_UNLOCK,
            patch_offset=patch_off, old_bytes=old_bytes, new_bytes=SPEED_PATCH_NEW,
            old_sha256=old_sha, new_sha256=new_sha,
            error="SHA-256 verification failed after patching"
        )

    return PatchResult(
        success=True, patch_type=PatchType.SPEED_UNLOCK,
        patch_offset=patch_off, old_bytes=old_bytes, new_bytes=SPEED_PATCH_NEW,
        old_sha256=old_sha, new_sha256=new_sha,
        output_data=bytes(patched),
    )
