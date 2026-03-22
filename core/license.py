"""
FlashMonkey License System — validates unlock keys with device binding.

License key format: FM-XXXX-XXXX-XXXX-XXXX (20 chars, Base32 encoded)

Local validation (offline mode):
- Key is HMAC-SHA256 signed with a server secret
- Encodes: product tier, creation timestamp, single-use flag
- Device binding: key is locked to scooter MAC + serial on first use

Server validation (online mode):
- POST /api/v1/validate with key + scooter MAC + serial
- Server returns: status, features, firmware download URL

(c) 2026 Martin Pfeffer | celox.io
"""

import hashlib
import hmac
import time
import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List


class Tier(Enum):
    SPEED_UNLOCK = "speed"
    ZERO_START = "zero_start"
    FULL_UNLOCK = "full"


@dataclass
class LicenseInfo:
    """Validated license information."""
    key: str
    tier: Tier
    features: List[str]
    bound_mac: Optional[str] = None
    bound_serial: Optional[str] = None
    activated_at: Optional[float] = None
    valid: bool = False
    error: Optional[str] = None


# Local license store
LICENSE_STORE = Path.home() / ".flashmonkey" / "licenses.json"


def _load_licenses() -> dict:
    if LICENSE_STORE.exists():
        return json.loads(LICENSE_STORE.read_text())
    return {}


def _save_licenses(data: dict):
    LICENSE_STORE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_STORE.write_text(json.dumps(data, indent=2))


def validate_key_format(key: str) -> bool:
    """Check if key matches FM-XXXX-XXXX-XXXX-XXXX format."""
    parts = key.strip().upper().split('-')
    if len(parts) != 5 or parts[0] != 'FM':
        return False
    return all(len(p) == 4 and p.isalnum() for p in parts[1:])


def activate_license(key: str, scooter_mac: str, scooter_serial: str) -> LicenseInfo:
    """Activate a license key and bind to a specific scooter.

    In production, this would call the FlashMonkey backend.
    For local testing, it validates format and stores locally.
    """
    if not validate_key_format(key):
        return LicenseInfo(key=key, tier=Tier.FULL_UNLOCK, features=[],
                          valid=False, error="Invalid key format (expected FM-XXXX-XXXX-XXXX-XXXX)")

    licenses = _load_licenses()

    # Check if already activated
    if key in licenses:
        stored = licenses[key]
        if stored.get('bound_mac') and stored['bound_mac'] != scooter_mac:
            return LicenseInfo(
                key=key, tier=Tier(stored.get('tier', 'full')), features=[],
                bound_mac=stored['bound_mac'],
                valid=False, error=f"Key already bound to different scooter ({stored['bound_mac']})"
            )
        # Re-activation on same device
        return LicenseInfo(
            key=key, tier=Tier(stored.get('tier', 'full')),
            features=stored.get('features', ['speed_unlock', 'zero_start']),
            bound_mac=scooter_mac, bound_serial=scooter_serial,
            activated_at=stored.get('activated_at'),
            valid=True,
        )

    # New activation — in production this would call the backend
    # For local dev: accept any correctly formatted key
    tier = Tier.FULL_UNLOCK
    features = ['speed_unlock', 'zero_start']

    license_data = {
        'tier': tier.value,
        'features': features,
        'bound_mac': scooter_mac,
        'bound_serial': scooter_serial,
        'activated_at': time.time(),
    }
    licenses[key] = license_data
    _save_licenses(licenses)

    return LicenseInfo(
        key=key, tier=tier, features=features,
        bound_mac=scooter_mac, bound_serial=scooter_serial,
        activated_at=license_data['activated_at'],
        valid=True,
    )


def get_active_license(scooter_mac: str) -> Optional[LicenseInfo]:
    """Check if there's an active license for a given scooter."""
    licenses = _load_licenses()
    for key, data in licenses.items():
        if data.get('bound_mac') == scooter_mac:
            return LicenseInfo(
                key=key, tier=Tier(data.get('tier', 'full')),
                features=data.get('features', []),
                bound_mac=scooter_mac,
                bound_serial=data.get('bound_serial'),
                activated_at=data.get('activated_at'),
                valid=True,
            )
    return None
