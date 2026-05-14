from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class GeocoderSettings:
    provider: str
    base_url: str
    reverse_base_url: str
    timeout: float
    user_agent: str


@lru_cache(maxsize=1)
def get_settings() -> GeocoderSettings:
    return GeocoderSettings(
        provider=os.getenv("GEOCODER_PROVIDER", "nominatim"),
        base_url=os.getenv("GEOCODER_BASE_URL", "https://nominatim.openstreetmap.org/search"),
        reverse_base_url=os.getenv("GEOCODER_REVERSE_BASE_URL", "https://nominatim.openstreetmap.org/reverse"),
        timeout=float(os.getenv("GEOCODER_TIMEOUT", "10")),
        user_agent=os.getenv(
            "GEOCODER_USER_AGENT",
            "real-estate-mvp-geocode/0.1 (local development)",
        ),
    )
