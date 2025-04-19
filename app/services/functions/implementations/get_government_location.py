import math
from typing import List, Dict, Tuple, Optional

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en kilómetros entre dos puntos geográficos 
    usando la fórmula de Haversine.
    
    Args:
        lat1, lon1: Latitud y longitud del primer punto
        lat2, lon2: Latitud y longitud del segundo punto
        
    Returns:
        float: Distancia en kilómetros
    """
    # Radio de la Tierra en kilómetros
    radius = 6371.0
    
    # Convertir grados a radianes
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Diferencia de latitudes y longitudes
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    # Fórmula de Haversine
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = radius * c
    
    return distance

def get_nearest_office(user_lat: float, user_lon: float, office_type: str) -> Dict:
    """
    Encuentra la oficina más cercana a la ubicación del usuario.
    
    Args:
        user_lat: Latitud del usuario
        user_lon: Longitud del usuario
        office_type: Tipo de oficina ('registro_civil' o 'centro_comunitario')
        
    Returns:
        dict: Información de la oficina más cercana incluyendo distancia
    """
    # Definir las ubicaciones de las oficinas (hardcoded por ahora, después se pueden mover a base de datos)
    if office_type.lower() == 'registro_civil':
        offices = [
            {
                "name": "Registro Civil 1 - Palacio Municipal",
                "address": "Juárez y Libertad S/N, Centro de San Pedro",
                "lat": 25.6610729,
                "lon": -100.4004278,
                "phone": "(81) 8400-4400",
                "schedule": "Lunes a Viernes 8:00 AM - 3:00 PM"
            },
            {
                "name": "Registro Civil 2 - Valle Oriente",
                "address": "Av. Lázaro Cárdenas 1000, Valle del Mirador",
                "lat": 25.6497345,
                "lon": -100.3376872,
                "phone": "(81) 8478-2992",
                "schedule": "Lunes a Viernes 8:00 AM - 3:00 PM"
            },
            {
                "name": "Registro Civil 3 - Obispo",
                "address": "Corregidora 507, Centro de San Pedro",
                "lat": 25.6638318,
                "lon": -100.3981239,
                "phone": "(81) 8400-4600",
                "schedule": "Lunes a Viernes 8:00 AM - 3:00 PM"
            }
        ]
    elif office_type.lower() == 'centro_comunitario':
        offices = [
            {
                "name": "Centro Comunitario San Pedro 400",
                "address": "Avenida Las Torres y Pensilvania S/N, Col. San Pedro 400",
                "lat": 25.6861755,
                "lon": -100.4333818,
                "phone": "(81) 8242-9001",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            },
            {
                "name": "Centro Comunitario El Obispo",
                "address": "Porfirio Díaz, entre Corregidora y Degollado, Col. El Obispo",
                "lat": 25.6636286,
                "lon": -100.3997121,
                "phone": "(81) 8336-7483",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            },
            {
                "name": "Centro Comunitario Los Pinos",
                "address": "Cedro entre Mezquite y Fresnos, Col. Los Pinos",
                "lat": 25.6731652,
                "lon": -100.4201358,
                "phone": "(81) 8336-5182",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            },
            {
                "name": "Centro Comunitario Revolución",
                "address": "Villas del Obispo, Col. Revolución 5to sector",
                "lat": 25.6781639,
                "lon": -100.3918756,
                "phone": "(81) 8242-9001",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            },
            {
                "name": "Centro Comunitario Canteras",
                "address": "Lago Rodolfo y Lago Herradura, Col. Canteras",
                "lat": 25.6493222,
                "lon": -100.3867894,
                "phone": "(81) 8242-9001",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            },
            {
                "name": "Centro Comunitario San Pedro",
                "address": "Oaxaca y Guerrero, Col. Unidad San Pedro",
                "lat": 25.6742194,
                "lon": -100.4067576,
                "phone": "(81) 8242-9001",
                "schedule": "Lunes a Viernes 9:00 AM - 6:00 PM"
            }
        ]
    else:
        # Tipo de oficina no soportado
        return {
            "error": f"Tipo de oficina '{office_type}' no soportado. Opciones válidas: 'registro_civil', 'centro_comunitario'"
        }
    
    # Calcular la distancia a cada oficina
    nearest_office = None
    min_distance = float('inf')
    
    for office in offices:
        distance = calculate_distance(user_lat, user_lon, office["lat"], office["lon"])
        
        # Guardar la distancia calculada en la información de la oficina
        office["distance"] = round(distance, 2)
        
        if distance < min_distance:
            min_distance = distance
            nearest_office = office
    
    # Ordenar todas las oficinas por distancia para poder mostrar alternativas
    offices_sorted = sorted(offices, key=lambda x: x["distance"])
    
    return {
        "nearest": nearest_office,
        "all_sorted": offices_sorted
    }

async def find_nearest_government_office(latitude: float, longitude: float, office_type: str) -> Dict:
    """
    Función para ser registrada en el function_manager.
    
    Args:
        latitude: Latitud del usuario
        longitude: Longitud del usuario
        office_type: Tipo de oficina ('registro_civil' o 'centro_comunitario')
        
    Returns:
        dict: Resultado con la oficina más cercana y todas ordenadas por distancia
    """
    try:
        result = get_nearest_office(latitude, longitude, office_type)
        return {
            "success": True,
            "nearest_office": result["nearest"],
            "all_offices": result["all_sorted"][:3]  # Limitamos a las 3 más cercanas
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }