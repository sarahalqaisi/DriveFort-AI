"""Single source of truth for the DriveFort AI product identity.

The legacy project used several hard-coded ZoneGuard labels across the backend,
frontend and reports. V3 keeps identity metadata here so future renames do not
require editing security or simulation logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Tuple


@dataclass(frozen=True)
class BrandIdentity:
    name: str = "DriveFort AI"
    short_name: str = "DriveFort"
    tagline: str = "Secure Intelligence for Electric Mobility"
    descriptor: str = "EV Cybersecurity & Digital Twin Platform"
    version: str = "3.1.0"
    pillars: Tuple[str, ...] = ("Protect", "Detect", "Twin", "Recover")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["pillars"] = list(self.pillars)
        return data


BRAND = BrandIdentity()
