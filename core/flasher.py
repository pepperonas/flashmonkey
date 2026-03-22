"""
FlashMonkey OTA Flasher — sends patched firmware to scooter via BLE.

Implements the complete Navee DFU protocol:
  1. BLE Connect + AES-128-ECB Auth
  2. "down dfu_start 1" -> "ok"
  3. "down ble_rand" -> XOR decrypt -> "down ble_key <decrypted>" -> "ok"
  4. Wait for 0x43 ('C') -> XMODEM Ready
  5. 1080 x 128-byte blocks (SOH + Seq + ~Seq + Data + CRC-16)
  6. EOT (0x04) -> "rsq dfu_ok"

This module wraps the existing ota_flasher.py logic into a clean API.

(c) 2026 Martin Pfeffer | celox.io
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class FlashState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    DFU_ENTRY = "dfu_entry"
    KEY_EXCHANGE = "key_exchange"
    XMODEM_READY = "xmodem_ready"
    TRANSFERRING = "transferring"
    EOT = "eot"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class FlashProgress:
    """Progress update during flashing."""
    state: FlashState
    blocks_sent: int = 0
    blocks_total: int = 0
    percent: float = 0.0
    message: str = ""
    error: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.state in (FlashState.SUCCESS, FlashState.FAILED)


# Type alias for progress callback
ProgressCallback = Callable[[FlashProgress], None]


async def flash_firmware(
    firmware_data: bytes,
    device_address: str,
    device_id: bytes,
    progress_cb: Optional[ProgressCallback] = None,
) -> bool:
    """Flash firmware to a Navee scooter via BLE OTA.

    Args:
        firmware_data: Complete firmware binary (OTA format, with correct SHA-256)
        device_address: BLE MAC address of the scooter
        device_id: 6-byte Navee device ID for authentication
        progress_cb: Optional callback for progress updates

    Returns:
        True if flash was successful (rsq dfu_ok received)
    """
    try:
        from bleak import BleakClient
    except ImportError:
        raise RuntimeError("bleak library required: pip3 install bleak")

    def report(state: FlashState, **kwargs):
        if progress_cb:
            progress_cb(FlashProgress(state=state, **kwargs))

    report(FlashState.CONNECTING, message=f"Connecting to {device_address}...")

    # TODO: Integrate the full OTA flasher logic from navee/tools/ota_flasher.py
    # For now, this is a placeholder that shows the API structure.
    # The actual implementation will reuse NaveeOTAFlasher from the navee repo.

    report(FlashState.FAILED, error="OTA flasher integration pending — use tools/ota_flasher.py directly")
    return False
