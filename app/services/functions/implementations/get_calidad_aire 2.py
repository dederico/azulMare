import aiohttp
import asyncio
from app.util.logger import logger

async def get_calidad_aire():
    """Obtener información actual sobre la calidad del aire en San Pedro Garza García.

    Returns:
        string: Resumen actual de la calidad del aire para usar en la respuesta del bot.
    """
    try:
        url = "https://api-stage.sanpedro.gob.mx/api/Util/aire/aqi-suroeste2"
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    resumen = data.get("resumen", "")
                    
                    if resumen:
                        return resumen
                    else:
                        # Fallback si no viene el campo resumen
                        categoria = data.get("categoria", "No disponible")
                        aqi = data.get("aqi", "No disponible")
                        return f"Calidad del aire: {categoria} (ICA: {aqi})"
                else:
                    return "La información de calidad del aire no está disponible en este momento."
                    
    except Exception as e:
        logger.error(f"Error al obtener calidad del aire: {str(e)}")
        return "No se pudo obtener la información de calidad del aire en este momento."