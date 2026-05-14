from __future__ import annotations

from dataclasses import dataclass
import re

import httpx

from model.apps.geocode.config import GeocoderSettings


class AddressNotFoundError(Exception):
    pass


class GeocodingProviderUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class GeocodingResult:
    latitude: str
    longitude: str
    address: dict[str, str | None] | None = None
    quality: str = "coordinates_only"


@dataclass(frozen=True)
class ReverseGeocodingResult:
    latitude: str
    longitude: str
    address: dict[str, str | None]
    quality: str


MOSCOW_ADMIN_PART_PATTERN = re.compile(
    r"^(?:[СC](?:[ЗZ]|[ВB])?АО|[ЮY](?:[ЗZ]|[ВB])?АО|[ВB]АО|[ЗZ]АО|ЦАО|ТАО|НАО|ТиНАО)$",
    flags=re.IGNORECASE,
)
DISTRICT_PREFIX_PATTERN = re.compile(r"^(?:р-н|район)\s+", flags=re.IGNORECASE)
HOUSE_PREFIX_PATTERN = re.compile(r"^(?:д\.?|дом)\s*(?P<house>\d.*)$", flags=re.IGNORECASE)
BARE_HOUSE_PATTERN = re.compile(r"^\d+[а-яa-z0-9/-]*$", flags=re.IGNORECASE)
BUILDING_SUFFIX_PATTERN = re.compile(r"^(?P<house>\d+)\s*[сc]\s*(?P<building>\d+)$", flags=re.IGNORECASE)


class GeocodingService:
    def __init__(self, settings: GeocoderSettings) -> None:
        self._settings = settings

    async def geocode(self, address: str) -> GeocodingResult:
        if self._settings.provider != "nominatim":
            raise GeocodingProviderUnavailableError("Unsupported geocoding provider.")

        for query in _build_nominatim_queries(address):
            payload = await self._request_nominatim(query)
            if not payload:
                continue

            first_result = payload[0]
            if not isinstance(first_result, dict):
                raise GeocodingProviderUnavailableError("Unexpected geocoding provider response.")

            latitude = first_result.get("lat")
            longitude = first_result.get("lon")
            if not isinstance(latitude, str) or not isinstance(longitude, str):
                raise GeocodingProviderUnavailableError("Unexpected geocoding provider response.")

            address = _extract_address_fields(first_result)
            return GeocodingResult(
                latitude=latitude,
                longitude=longitude,
                address=address,
                quality=_address_quality(address),
            )

        raise AddressNotFoundError("Address not found.")

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseGeocodingResult:
        if self._settings.provider != "nominatim":
            raise GeocodingProviderUnavailableError("Unsupported geocoding provider.")

        payload = await self._request_nominatim_reverse(latitude, longitude)
        address = _extract_address_fields(payload)
        if not address.get("full_address"):
            raise AddressNotFoundError("Address not found.")
        return ReverseGeocodingResult(
            latitude=str(latitude),
            longitude=str(longitude),
            address=address,
            quality=_address_quality(address),
        )

    async def _request_nominatim(self, address: str) -> list[object]:
        params = {
            "q": address,
            "format": "jsonv2",
            "limit": "1",
            "addressdetails": "1",
        }
        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout) as client:
                response = await client.get(
                    self._settings.base_url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise GeocodingProviderUnavailableError("Geocoding provider unavailable.") from exc

        if not isinstance(payload, list):
            raise GeocodingProviderUnavailableError("Unexpected geocoding provider response.")

        return payload

    async def _request_nominatim_reverse(self, latitude: float, longitude: float) -> dict[str, object]:
        params = {
            "lat": str(latitude),
            "lon": str(longitude),
            "format": "jsonv2",
            "addressdetails": "1",
        }
        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.timeout) as client:
                response = await client.get(
                    self._settings.reverse_base_url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise GeocodingProviderUnavailableError("Geocoding provider unavailable.") from exc

        if not isinstance(payload, dict):
            raise GeocodingProviderUnavailableError("Unexpected geocoding provider response.")
        return payload


def _build_nominatim_queries(address: str) -> tuple[str, ...]:
    normalized_address = _normalize_address_text(address)
    candidates = [normalized_address]
    parts = [part.strip() for part in address.split(",") if part.strip()]
    house_index = _find_house_index(parts)

    if len(parts) >= 3 and house_index is not None:
        city = parts[0]
        street = _find_street_before_house(parts, house_index)
        house = _normalize_house_part(parts[house_index])
        district = _find_district_part(parts)
        if city and street and house:
            candidates.append(f"{street}, {house}, {city}, Россия")
            building_query = _build_house_with_building_query(street, house, city)
            if building_query is not None:
                candidates.append(building_query)
            candidates.append(f"{street}, {_strip_building_suffix(house)}, {city}, Россия")
            if district is not None:
                candidates.append(f"{street}, {house}, {district}, {city}, Россия")

    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)

    return tuple(unique_candidates)


def _normalize_address_text(address: str) -> str:
    return re.sub(r"\s+", " ", address).strip()


def _find_house_index(parts: list[str]) -> int | None:
    for index in range(len(parts) - 1, 0, -1):
        if _normalize_house_part(parts[index]):
            return index
    return None


def _normalize_house_part(part: str) -> str:
    normalized_part = _normalize_address_text(part)
    prefixed_match = HOUSE_PREFIX_PATTERN.fullmatch(normalized_part)
    if prefixed_match is not None:
        return _normalize_address_text(prefixed_match.group("house"))
    if BARE_HOUSE_PATTERN.fullmatch(normalized_part):
        return normalized_part
    return ""


def _find_street_before_house(parts: list[str], house_index: int) -> str | None:
    for index in range(house_index - 1, 0, -1):
        part = _normalize_address_text(parts[index])
        if not part or _is_admin_part(part) or DISTRICT_PREFIX_PATTERN.match(part):
            continue
        return part
    return None


def _find_district_part(parts: list[str]) -> str | None:
    for part in parts[1:]:
        normalized_part = _normalize_address_text(part)
        if DISTRICT_PREFIX_PATTERN.match(normalized_part):
            return DISTRICT_PREFIX_PATTERN.sub("", normalized_part).strip()
    return None


def _is_admin_part(part: str) -> bool:
    return MOSCOW_ADMIN_PART_PATTERN.fullmatch(part) is not None


def _build_house_with_building_query(street: str, house: str, city: str) -> str | None:
    match = BUILDING_SUFFIX_PATTERN.fullmatch(house)
    if match is None:
        return None
    return f"{street}, {match.group('house')} строение {match.group('building')}, {city}, Россия"


def _strip_building_suffix(house: str) -> str:
    match = BUILDING_SUFFIX_PATTERN.fullmatch(house)
    if match is None:
        return house
    return match.group("house")


def _extract_address_fields(payload: dict[str, object]) -> dict[str, str | None]:
    address_payload = payload.get("address")
    address = address_payload if isinstance(address_payload, dict) else {}
    road = _string_or_none(address.get("road") or address.get("pedestrian") or address.get("footway"))
    house = _string_or_none(address.get("house_number"))
    district = _string_or_none(
        address.get("suburb")
        or address.get("city_district")
        or address.get("borough")
        or address.get("district")
    )
    city = _string_or_none(
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
    )
    region = _string_or_none(address.get("state") or address.get("region"))
    full_address = _string_or_none(payload.get("display_name"))
    return {
        "street": road,
        "house": house,
        "district": district,
        "city": city,
        "region": region,
        "full_address": full_address,
    }


def _address_quality(address: dict[str, str | None]) -> str:
    if address.get("street") and address.get("house") and address.get("city"):
        return "street_house"
    if address.get("city") or address.get("region"):
        return "partial"
    return "coordinates_only"


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_address_text(value)
    return normalized or None
