import os
import httpx
import json
from datetime import datetime, timedelta
import pytz
from app.util.logger import logger

# Coordenadas fijas de San Pedro, Nuevo León, México
SAN_PEDRO_LAT = 25.6866
SAN_PEDRO_LON = -100.4422
SAN_PEDRO_NAME = "San Pedro, Nuevo León"

async def get_climate(days_ahead: int = 0):
    """
    Obtiene información del clima para San Pedro, Nuevo León.
    
    Args:
        days_ahead (int): Días hacia adelante (0 = hoy, 1 = mañana, etc.). 
                         Máximo 5 días. Por defecto es 0 (hoy).
    
    Returns:
        str: Información detallada del clima para San Pedro.
    """
    try:
        # Validar días
        if days_ahead < 0:
            days_ahead = 0
        elif days_ahead > 5:
            days_ahead = 5
            
        # Obtener API key de OpenWeatherMap
        api_key = "f45b4e58d424376031c3af0a132f5d4d"
        #os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            return "❌ No se pudo obtener la información del clima. API key no configurada."
        
        # Zona horaria de México
        mexico_tz = pytz.timezone('America/Mexico_City')
        
        if days_ahead == 0:
            # Clima actual
            current_url = f"https://api.openweathermap.org/data/2.5/weather"
            params = {
                "lat": SAN_PEDRO_LAT,
                "lon": SAN_PEDRO_LON,
                "appid": api_key,
                "units": "metric",
                "lang": "es"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(current_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            # Extraer información del clima actual
            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            description = data["weather"][0]["description"].title()
            wind_speed = data["wind"]["speed"]
            
            current_time = datetime.now(mexico_tz)
            
            climate_info = f"🌤️ **Clima en {SAN_PEDRO_NAME}**\n"
            climate_info += f"📅 **Hoy, {current_time.strftime('%d de %B de %Y')}**\n\n"
            climate_info += f"🌡️ **Temperatura:** {temp:.1f}°C\n"
            climate_info += f"🤔 **Sensación térmica:** {feels_like:.1f}°C\n"
            climate_info += f"☁️ **Condiciones:** {description}\n"
            climate_info += f"💧 **Humedad:** {humidity}%\n"
            climate_info += f"💨 **Viento:** {wind_speed:.1f} m/s\n"
            
            # Agregar recomendaciones
            if temp < 15:
                climate_info += f"\n🧥 **Recomendación:** Abrígate bien, hace frío."
            elif temp > 30:
                climate_info += f"\n☀️ **Recomendación:** Mantente hidratado, hace calor."
            elif humidity > 80:
                climate_info += f"\n💦 **Recomendación:** Día húmedo, considera llevar paraguas."
                
        else:
            # Pronóstico (para días futuros)
            forecast_url = f"https://api.openweathermap.org/data/2.5/forecast"
            params = {
                "lat": SAN_PEDRO_LAT,
                "lon": SAN_PEDRO_LON,
                "appid": api_key,
                "units": "metric",
                "lang": "es"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(forecast_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            # Buscar el pronóstico para el día solicitado (mediodía aprox.)
            target_date = datetime.now(mexico_tz) + timedelta(days=days_ahead)
            target_day_str = target_date.strftime('%Y-%m-%d')
            
            forecast_item = None
            for item in data["list"]:
                forecast_time = datetime.fromtimestamp(item["dt"], mexico_tz)
                if (forecast_time.strftime('%Y-%m-%d') == target_day_str and 
                    10 <= forecast_time.hour <= 14):  # Buscar entre 10am y 2pm
                    forecast_item = item
                    break
            
            if not forecast_item:
                # Si no encontramos mediodía, tomar el primer pronóstico del día
                for item in data["list"]:
                    forecast_time = datetime.fromtimestamp(item["dt"], mexico_tz)
                    if forecast_time.strftime('%Y-%m-%d') == target_day_str:
                        forecast_item = item
                        break
            
            if not forecast_item:
                return f"❌ No se encontró pronóstico para dentro de {days_ahead} días."
            
            # Extraer información del pronóstico
            temp = forecast_item["main"]["temp"]
            temp_min = forecast_item["main"]["temp_min"]
            temp_max = forecast_item["main"]["temp_max"]
            humidity = forecast_item["main"]["humidity"]
            description = forecast_item["weather"][0]["description"].title()
            wind_speed = forecast_item["wind"]["speed"]
            
            # Probabilidad de lluvia si está disponible
            rain_prob = forecast_item.get("pop", 0) * 100 if "pop" in forecast_item else 0
            
            day_name = target_date.strftime('%A').title()
            day_names = {
                'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
            }
            day_name = day_names.get(day_name, day_name)
            
            climate_info = f"🌤️ **Pronóstico para {SAN_PEDRO_NAME}**\n"
            if days_ahead == 1:
                climate_info += f"📅 **Mañana, {day_name} {target_date.strftime('%d de %B')}**\n\n"
            else:
                climate_info += f"📅 **{day_name} {target_date.strftime('%d de %B')} (en {days_ahead} días)**\n\n"
            
            climate_info += f"🌡️ **Temperatura:** {temp:.1f}°C (Min: {temp_min:.1f}°C, Max: {temp_max:.1f}°C)\n"
            climate_info += f"☁️ **Condiciones:** {description}\n"
            climate_info += f"💧 **Humedad:** {humidity}%\n"
            climate_info += f"💨 **Viento:** {wind_speed:.1f} m/s\n"
            
            if rain_prob > 0:
                climate_info += f"🌧️ **Probabilidad de lluvia:** {rain_prob:.0f}%\n"
            
            # Recomendaciones para el futuro
            if rain_prob > 50:
                climate_info += f"\n☔ **Recomendación:** Lleva paraguas, hay alta probabilidad de lluvia."
            elif temp_max > 32:
                climate_info += f"\n☀️ **Recomendación:** Día caluroso, usa protector solar y mantente hidratado."
            elif temp_min < 10:
                climate_info += f"\n🧥 **Recomendación:** Mañana fría, abrígate bien."
        
        logger.info(f"Información del clima obtenida para San Pedro (días +{days_ahead})")
        return climate_info
        
    except httpx.TimeoutException:
        error_msg = f"❌ Tiempo de espera agotado al obtener el clima de {SAN_PEDRO_NAME}."
        logger.error(error_msg)
        return error_msg
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            error_msg = "❌ Error de autenticación con el servicio del clima. API key inválida."
        elif e.response.status_code == 429:
            error_msg = "❌ Límite de consultas excedido. Intenta de nuevo más tarde."
        else:
            error_msg = f"❌ Error al obtener el clima: {e.response.status_code}"
        logger.error(error_msg)
        return error_msg
        
    except Exception as e:
        error_msg = f"❌ Error inesperado al obtener el clima de {SAN_PEDRO_NAME}: {str(e)}"
        logger.error(error_msg)
        return error_msg


# Función para registrar en el sistema
def register_climate_function():
    """
    Función helper para registrar get_climate en el sistema de funciones.
    """
    return {
        "name": "get_climate",
        "description": "Obtiene información del clima para San Pedro, Nuevo León. Por defecto muestra el clima de hoy, pero puede consultar hasta 5 días hacia adelante.",
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Días hacia adelante para consultar el clima. 0 = hoy (por defecto), 1 = mañana, 2 = pasado mañana, etc. Máximo 5 días.",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0
                }
            }
        }
    }