"""
FlashMonkey BLE Scanner — finds Navee scooters.

(c) 2026 Martin Pfeffer | celox.io
"""

import asyncio
import struct
from dataclasses import dataclass
from typing import List, Optional

try:
    from bleak import BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False


SCOOTER_NAME_PREFIXES = ("NAVEE", "NV", "ST3")
SERVICE_UUID = "0000d0ff-3c17-d293-8e48-14fe2e4da212"


@dataclass
class ScooterInfo:
    """Discovered scooter."""
    name: str
    address: str
    rssi: int
    pid: Optional[int] = None  # Product ID from scan record

    @property
    def market(self) -> str:
        if self.pid == 23452:
            return "DE (22 km/h)"
        elif self.pid == 23451:
            return "Global (30 km/h)"
        else:
            return f"Unknown (PID {self.pid})" if self.pid else "Unknown"


async def scan_for_scooters(timeout: float = 10.0) -> List[ScooterInfo]:
    """Scan for Navee scooters via BLE."""
    if not HAS_BLEAK:
        raise RuntimeError("bleak library required: pip3 install bleak")

    found = []
    devices = await BleakScanner.discover(timeout=timeout)

    for d in devices:
        name = d.name or ""
        if any(name.upper().startswith(p) for p in SCOOTER_NAME_PREFIXES):
            rssi = getattr(d, 'rssi', None) or -100

            # Try to extract PID from advertisement data
            pid = None
            if hasattr(d, 'metadata') and 'manufacturer_data' in d.metadata:
                for _, mdata in d.metadata['manufacturer_data'].items():
                    if len(mdata) >= 8:
                        pid = struct.unpack('<H', mdata[6:8])[0]

            found.append(ScooterInfo(
                name=name,
                address=d.address,
                rssi=rssi,
                pid=pid,
            ))

    return sorted(found, key=lambda s: s.rssi, reverse=True)
