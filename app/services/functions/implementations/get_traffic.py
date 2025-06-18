import os
import httpx
import json
from datetime import datetime, timedelta
import pytz
from app.util.logger import logger
import urllib.parse

# Coordenadas y puntos de referencia de San Pedro, Nuevo León
SAN_PEDRO_CENTER = {"lat": 25.6866, "lng": -100.4422}
SAN_PEDRO_NAME = "San Pedro, Nuevo León"

# Puntos importantes de San Pedro para análisis de tráfico
IMPORTANT_POINTS = {
    "centro": {"lat": 25.6866, "lng": -100.4422, "name": "Centro de San Pedro"},
    "garza_sada": {"lat": 25.6512, "lng": -100.4033, "name": "Av. Garza Sada"},
    "gonzalitos": {"lat": 25.6789, "lng": -100.4156, "name": "Av. Gonzalitos"},
    "lazaro_cardenas": {"lat": 25.6923, "lng": -100.4234, "name": "Av. Lázaro Cárdenas"},
    "vasconcelos": {"lat": 25.6634, "lng": -100.4178, "name": "Av. Vasconcelos"},
    "plaza_la_silla": {"lat": 25.6598, "lng": -100.4089, "name": "Plaza La Silla"}
}

async def get_traffic(origin: str = None, destination: str = None, check_routes: bool = True):
    """
    Obtiene información del tráfico en San Pedro, Nuevo León.
    
    Args:
        origin (string): Punto de origen (opcional). Puede ser una dirección o punto de referencia.
        destination (string): Punto de destino (opcional). Puede ser una dirección o punto de referencia.
        check_routes (boolean): Si revisar rutas principales cuando no se especifica origen/destino.
    
    Returns:
        sting: Información detallada del tráfico en San Pedro.
    """
    try:
        # Obtener API key de Google Maps
        api_key = "AIzaSyDQeA8Ay6UfjVXJV1wV-z_cl35iyleXu2c"
        #os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return "❌ No se pudo obtener la información del tráfico. Google Maps API key no configurada."
        
        # Zona horaria de México
        mexico_tz = pytz.timezone('America/Mexico_City')
        current_time = datetime.now(mexico_tz)
        
        traffic_info = f"🚗 **Información de Tráfico en {SAN_PEDRO_NAME}**\n"
        traffic_info += f"📅 **{current_time.strftime('%A %d de %B, %Y - %I:%M %p')}**\n"
        traffic_info += f"📍 *Datos proporcionados por Google Maps*\n\n"
        
        if origin and destination:
            # Consulta de ruta específica
            traffic_info += await _get_specific_route_info(api_key, origin, destination)
            
        elif origin or destination:
            # Si solo se proporciona origen o destino, asumir el otro como centro de San Pedro
            if origin:
                destination = "San Pedro, Nuevo León, México"
                route_type = f"desde {origin}"
            else:
                origin = "San Pedro, Nuevo León, México"
                route_type = f"hacia {destination}"
                
            traffic_info += f"🎯 **Ruta {route_type}:**\n"
            traffic_info += "*Datos de Google Maps*\n"
            traffic_info += await _get_specific_route_info(api_key, origin, destination)
            
        else:
            # Información general de tráfico en San Pedro
            if check_routes:
                traffic_info += await _get_general_traffic_info(api_key)
            else:
                traffic_info += await _get_traffic_conditions_summary(api_key)
        
        # Agregar recomendaciones generales
        traffic_info += _get_traffic_recommendations(current_time)
        
        logger.info(f"Información de tráfico obtenida para San Pedro")
        return traffic_info
        
    except Exception as e:
        error_msg = f"❌ Error inesperado al obtener información de tráfico: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def _get_specific_route_info(api_key: str, origin: str, destination: str):
    """Obtiene información de una ruta específica."""
    try:
        # Geocodificar direcciones si es necesario
        origin_coords = await _geocode_address(api_key, origin)
        dest_coords = await _geocode_address(api_key, destination)
        
        if not origin_coords or not dest_coords:
            return "❌ No se pudieron encontrar las ubicaciones especificadas en Google Maps.\n\n"
        
        # Obtener rutas con información de tráfico
        directions_url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": f"{origin_coords['lat']},{origin_coords['lng']}",
            "destination": f"{dest_coords['lat']},{dest_coords['lng']}",
            "departure_time": "now",
            "traffic_model": "best_guess",
            "alternatives": "true",
            "key": api_key
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(directions_url, params=params)
            response.raise_for_status()
            data = response.json()
        
        if data["status"] != "OK" or not data.get("routes"):
            return "❌ No se encontraron rutas para los puntos especificados en Google Maps.\n\n"
        
        route_info = ""
        for i, route in enumerate(data["routes"][:2]):  # Máximo 2 rutas
            leg = route["legs"][0]
            duration = leg["duration"]["text"]
            duration_in_traffic = leg.get("duration_in_traffic", {}).get("text", duration)
            distance = leg["distance"]["text"]
            
            route_name = f"Ruta {i+1}"
            if route.get("summary"):
                route_name += f" (vía {route['summary']})"
            
            route_info += f"🛣️ **{route_name}:**\n"
            route_info += f"   📍 Distancia: {distance}\n"
            route_info += f"   ⏱️ Tiempo sin tráfico: {duration}\n"
            route_info += f"   🚦 Tiempo con tráfico: {duration_in_traffic}\n"
            
            # Calcular retraso por tráfico
            try:
                normal_minutes = _extract_minutes(duration)
                traffic_minutes = _extract_minutes(duration_in_traffic)
                delay = traffic_minutes - normal_minutes
                
                if delay > 10:
                    route_info += f"   🔴 Tráfico pesado (+{delay} min)\n"
                elif delay > 5:
                    route_info += f"   🟡 Tráfico moderado (+{delay} min)\n"
                else:
                    route_info += f"   🟢 Tráfico fluido\n"
            except:
                route_info += f"   ℹ️ Condiciones de tráfico normales\n"
            
            route_info += "\n"
        
        return route_info
        
    except Exception as e:
        logger.error(f"Error obteniendo ruta específica: {str(e)}")
        return "❌ Error al obtener información de la ruta desde Google Maps.\n\n"


async def _get_general_traffic_info(api_key: str):
    """Obtiene información general de tráfico en puntos importantes."""
    try:
        traffic_info = "📊 **Condiciones en vías principales:**\n"
        traffic_info += "*Fuente: Google Maps Traffic*\n\n"
        
        # Revisar algunas rutas importantes dentro de San Pedro
        important_routes = [
            ("centro", "garza_sada", "Centro → Garza Sada"),
            ("gonzalitos", "vasconcelos", "Gonzalitos → Vasconcelos"),
            ("centro", "plaza_la_silla", "Centro → Plaza La Silla")
        ]
        
        for origin_key, dest_key, route_name in important_routes:
            try:
                origin_point = IMPORTANT_POINTS[origin_key]
                dest_point = IMPORTANT_POINTS[dest_key]
                
                directions_url = "https://maps.googleapis.com/maps/api/directions/json"
                params = {
                    "origin": f"{origin_point['lat']},{origin_point['lng']}",
                    "destination": f"{dest_point['lat']},{dest_point['lng']}",
                    "departure_time": "now",
                    "traffic_model": "best_guess",
                    "key": api_key
                }
                
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(directions_url, params=params)
                    
                if response.status_code == 200:
                    data = response.json()
                    if data["status"] == "OK" and data.get("routes"):
                        leg = data["routes"][0]["legs"][0]
                        duration = leg["duration"]["text"]
                        duration_in_traffic = leg.get("duration_in_traffic", {}).get("text", duration)
                        
                        try:
                            normal_minutes = _extract_minutes(duration)
                            traffic_minutes = _extract_minutes(duration_in_traffic)
                            delay = traffic_minutes - normal_minutes
                            
                            if delay > 8:
                                status = "🔴 Congestionado"
                            elif delay > 3:
                                status = "🟡 Moderado"
                            else:
                                status = "🟢 Fluido"
                                
                            traffic_info += f"• **{route_name}:** {status} ({duration_in_traffic})\n"
                        except:
                            traffic_info += f"• **{route_name}:** Tiempo normal ({duration})\n"
                            
            except Exception as route_error:
                logger.warning(f"Error en ruta {route_name}: {str(route_error)}")
                continue
        
        traffic_info += "\n"
        return traffic_info
        
    except Exception as e:
        logger.error(f"Error obteniendo tráfico general: {str(e)}")
        return "ℹ️ **Condiciones generales:** No disponibles en este momento.\n*Google Maps temporalmente no disponible*\n\n"


async def _get_traffic_conditions_summary(api_key: str):
    """Obtiene un resumen de condiciones de tráfico."""
    mexico_tz = pytz.timezone('America/Mexico_City')
    current_time = datetime.now(mexico_tz)
    hour = current_time.hour
    
    # Análisis basado en hora del día
    if 7 <= hour <= 9:
        summary = "🌅 **Hora pico matutina:** Se esperan retrasos en las principales avenidas.\n"
    elif 18 <= hour <= 20:
        summary = "🌆 **Hora pico vespertina:** Tráfico intenso en salidas de la ciudad.\n"
    elif 12 <= hour <= 14:
        summary = "☀️ **Hora de comida:** Tráfico moderado en zonas comerciales.\n"
    elif 22 <= hour or hour <= 6:
        summary = "🌙 **Madrugada:** Tráfico ligero, circulación fluida.\n"
    else:
        summary = "📈 **Horario regular:** Condiciones normales de tráfico.\n"
    
    return summary + "\n"


async def _geocode_address(api_key: str, address: str):
    """Geocodifica una dirección."""
    try:
        # Si la dirección es una de nuestras referencias conocidas
        address_lower = address.lower()
        for key, point in IMPORTANT_POINTS.items():
            if key in address_lower or point["name"].lower() in address_lower:
                return point
        
        # Geocodificación con Google Maps API
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": f"{address}, San Pedro, Nuevo León, México",
            "key": api_key
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(geocode_url, params=params)
            
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                return {"lat": location["lat"], "lng": location["lng"]}
        
        return None
        
    except Exception as e:
        logger.error(f"Error geocodificando dirección: {str(e)}")
        return None


def _extract_minutes(duration_text: str) -> int:
    """Extrae minutos de texto como '15 min' o '1 h 30 min'."""
    try:
        total_minutes = 0
        parts = duration_text.lower().split()
        
        for i, part in enumerate(parts):
            if 'h' in part and i > 0:
                total_minutes += int(parts[i-1]) * 60
            elif 'min' in part and i > 0:
                total_minutes += int(parts[i-1])
                
        return total_minutes if total_minutes > 0 else 15  # Default
    except:
        return 15  # Default fallback


def _get_traffic_recommendations(current_time):
    """Genera recomendaciones basadas en la hora."""
    hour = current_time.hour
    day_of_week = current_time.weekday()  # 0 = Monday, 6 = Sunday
    
    recommendations = "\n💡 **Recomendaciones:**\n"
    
    # Recomendaciones por hora
    if 7 <= hour <= 9:
        recommendations += "• Considera salir 15-20 minutos antes de lo normal\n"
        recommendations += "• Usa rutas alternas para evitar avenidas principales\n"
    elif 18 <= hour <= 20:
        recommendations += "• Evita salir entre 6:00 y 7:00 PM si es posible\n"
        recommendations += "• Considera usar transporte público\n"
    elif 12 <= hour <= 14:
        recommendations += "• Planifica tiempo extra para llegar a restaurantes\n"
    
    # Recomendaciones por día
    if day_of_week < 5:  # Lunes a Viernes
        recommendations += "• Consulta apps de tráfico antes de salir\n"
    else:  # Fin de semana
        recommendations += "• Tráfico ligero en general, pero cuidado en centros comerciales\n"
    
    recommendations += "• Para emergencias: contacta C4 al 81 89 88 2000\n"
    recommendations += "\n*Información de tráfico cortesía de Google Maps*"
    
    return recommendations
