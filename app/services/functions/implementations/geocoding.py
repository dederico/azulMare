import asyncio
from typing import Any

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError


_STREET_COMPONENTS = (
    "road",
    "pedestrian",
    "residential",
    "service",
    "path",
    "footway",
)
_COLONY_COMPONENTS = (
    "neighbourhood",
    "suburb",
    "quarter",
    "residential",
)


def _first_address_component(
    address: dict[str, Any],
    component_names: tuple[str, ...],
) -> str:
    for component_name in component_names:
        value = " ".join(str(address.get(component_name) or "").split()).strip()
        if value:
            return value
    return ""


async def reverse_geocode_location(
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Resolve a WhatsApp pin into structured address components.

    The geocoder is an external source, so callers must preserve the citizen's
    own answers as authoritative and use these values only for empty fields.
    Returning structured components prevents a formatted address from being
    copied wholesale into the wrong CIAC field.
    """
    geolocator = Nominatim(user_agent="sam-spgg-report-location/1.0")

    try:
        location = await asyncio.to_thread(
            geolocator.reverse,
            (float(latitude), float(longitude)),
            exactly_one=True,
            language="es",
            addressdetails=True,
            zoom=18,
            timeout=5,
        )
    except (GeocoderTimedOut, GeocoderServiceError, ValueError) as exc:
        return {
            "success": False,
            "formatted_address": "",
            "street": "",
            "number": "",
            "colony": "",
            "error": str(exc),
        }

    if not location:
        return {
            "success": False,
            "formatted_address": "",
            "street": "",
            "number": "",
            "colony": "",
            "error": "address_not_found",
        }

    raw_address = getattr(location, "raw", {}).get("address", {}) or {}
    return {
        "success": True,
        "formatted_address": " ".join(
            str(getattr(location, "address", "") or "").split()
        ).strip(),
        "street": _first_address_component(raw_address, _STREET_COMPONENTS),
        "number": " ".join(
            str(raw_address.get("house_number") or "").split()
        ).strip(),
        "colony": _first_address_component(raw_address, _COLONY_COMPONENTS),
        "raw_address": raw_address,
    }


async def latlong_to_address(latitude: float, longitude: float) -> str:
    """
    Convierte latitud y longitud a una dirección.

    Args:
        latitude (float): Latitud del punto.
        longitude (float): Longitud del punto.

    Returns:
        str: Dirección formateada o mensaje de error.
    """
    result = await reverse_geocode_location(latitude, longitude)
    if result.get("success") and result.get("formatted_address"):
        return str(result["formatted_address"])
    if result.get("error") and result["error"] != "address_not_found":
        return f"Error en la geocodificación: {result['error']}"
    return "No se pudo encontrar una dirección para las coordenadas proporcionadas."

# Ejemplo de uso
# address = await latlong_to_address(40.714224, -73.961452)
# print(address)
