from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

async def latlong_to_address(latitude: float, longitude: float) -> str:
    """
    Convierte latitud y longitud a una dirección.

    Args:
        latitude (float): Latitud del punto.
        longitude (float): Longitud del punto.

    Returns:
        str: Dirección formateada o mensaje de error.
    """
    geolocator = Nominatim(user_agent="myGeocoder")
    
    try:
        location = geolocator.reverse(f"{latitude}, {longitude}")
        if location:
            return location.address
        else:
            return "No se pudo encontrar una dirección para las coordenadas proporcionadas."
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        return f"Error en la geocodificación: {str(e)}"

# Ejemplo de uso
# address = await latlong_to_address(40.714224, -73.961452)
# print(address)