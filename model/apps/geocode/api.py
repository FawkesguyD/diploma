from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query, status

from model.apps.geocode.config import get_settings
from model.apps.geocode.schemas import AddressFields, GeocodeResponse, ReverseGeocodeResponse
from model.apps.geocode.service import (
    AddressNotFoundError,
    GeocodingProviderUnavailableError,
    GeocodingService,
)


app = FastAPI(
    title="Сервис геокодирования недвижимости",
    version="0.1.0",
)


@lru_cache(maxsize=1)
def get_geocoding_service() -> GeocodingService:
    return GeocodingService(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "provider": settings.provider}


@app.get("/geocode", response_model=GeocodeResponse)
async def geocode(
    address: str = Query(..., min_length=1),
    service: GeocodingService = Depends(get_geocoding_service),
) -> GeocodeResponse:
    normalized_address = address.strip()
    if not normalized_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Address must not be empty",
        )

    try:
        result = await service.geocode(normalized_address)
    except AddressNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found") from exc
    except GeocodingProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Geocoding provider unavailable",
        ) from exc

    return GeocodeResponse(
        address=normalized_address,
        latitude=result.latitude,
        longitude=result.longitude,
        normalized_address=AddressFields(**(result.address or {})),
        quality=result.quality,
    )


@app.get("/reverse-geocode", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    service: GeocodingService = Depends(get_geocoding_service),
) -> ReverseGeocodeResponse:
    try:
        result = await service.reverse_geocode(latitude, longitude)
    except AddressNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found") from exc
    except GeocodingProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Geocoding provider unavailable",
        ) from exc

    return ReverseGeocodeResponse(
        latitude=result.latitude,
        longitude=result.longitude,
        normalized_address=AddressFields(**result.address),
        quality=result.quality,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        reload=False,
    )
