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
        timeout = aiohttp.ClientTimeout(total=15)

        logger.info(f"Intentando obtener calidad del aire desde: {url}")

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                logger.info(f"Respuesta del API de calidad del aire: status={response.status}")

                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Datos recibidos del API: {data}")

                    resumen = data.get("resumen", "")
                    categoria = data.get("categoria", "No disponible")
                    aqi = data.get("aqi", "No disponible")

                    if resumen and resumen.strip():
                        return f"Calidad del aire: {resumen}"
                    else:
                        # Fallback si no viene el campo resumen
                        return f"Calidad del aire: {categoria} (ICA: {aqi})"
                else:
                    error_text = await response.text()
                    logger.error(f"Error HTTP {response.status} al obtener calidad del aire: {error_text}")
                    return "La información de calidad del aire no está disponible en este momento."

    except asyncio.TimeoutError:
        logger.error("Timeout al obtener calidad del aire (15 segundos)")
        return "No se pudo obtener la información de calidad del aire (timeout)."
    except Exception as e:
        logger.error(f"Error al obtener calidad del aire: {type(e).__name__}: {str(e)}")
        return "No se pudo obtener la información de calidad del aire en este momento."