from __future__ import annotations

import asyncio

import pandas as pd

from model.analytics.config import AnalyticsConfig
from model.apps.geocode.config import get_settings
from model.apps.geocode.service import AddressNotFoundError, GeocodingProviderUnavailableError, GeocodingService


async def _reverse_geocode_missing_districts(frame: pd.DataFrame, config: AnalyticsConfig) -> pd.DataFrame:
    service = GeocodingService(get_settings())
    enriched = frame.copy()
    mask = (
        enriched["district"].isna()
        & enriched["latitude"].notna()
        & enriched["longitude"].notna()
    )
    candidates = enriched.loc[mask].head(config.geocode_limit)

    for index, row in candidates.iterrows():
        try:
            result = await service.reverse_geocode(float(row["latitude"]), float(row["longitude"]))
        except (AddressNotFoundError, GeocodingProviderUnavailableError):
            continue
        district = (result.address or {}).get("district")
        if district:
            enriched.at[index, "district"] = district
            enriched.at[index, "district_group"] = district

    return enriched


def enrich_missing_districts(frame: pd.DataFrame, config: AnalyticsConfig) -> pd.DataFrame:
    if not config.enable_reverse_geocoding or frame.empty:
        return frame
    return asyncio.run(_reverse_geocode_missing_districts(frame, config))

