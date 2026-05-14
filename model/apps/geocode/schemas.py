from __future__ import annotations

from pydantic import BaseModel


class AddressFields(BaseModel):
    street: str | None = None
    house: str | None = None
    district: str | None = None
    city: str | None = None
    region: str | None = None
    full_address: str | None = None


class GeocodeResponse(BaseModel):
    address: str
    latitude: str
    longitude: str
    normalized_address: AddressFields | None = None
    quality: str = "coordinates_only"
    status: str = "ok"


class ReverseGeocodeResponse(BaseModel):
    latitude: str
    longitude: str
    normalized_address: AddressFields
    quality: str
    status: str = "ok"
