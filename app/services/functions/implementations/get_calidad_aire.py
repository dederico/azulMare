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

                    categoria = data.get("categoria", "No disponible")
                    aqi = data.get("aqi", "No disponible")
                    fecha = data.get("fecha", "")
                    principal = data.get("principal", "")
                    detalles = data.get("detalles", {})

                    # Construir mensaje detallado
                    mensaje = f"Calidad del aire en San Pedro Garza García:\n"
                    mensaje += f"• Estado: {categoria}\n"
                    mensaje += f"• Índice AQI: {aqi}\n"

                    if principal:
                        principal_nombre = {
                            "pm25": "PM2.5",
                            "pm10": "PM10",
                            "o3": "Ozono (O3)",
                            "no2": "Dióxido de Nitrógeno (NO2)",
                            "so2": "Dióxido de Azufre (SO2)",
                            "co": "Monóxido de Carbono (CO)"
                        }.get(principal, principal)
                        mensaje += f"• Contaminante principal: {principal_nombre}\n"

                    if detalles:
                        mensaje += f"• Detalles: PM2.5={detalles.get('pm25', 'N/A')}, PM10={detalles.get('pm10', 'N/A')}, O3={detalles.get('o3', 'N/A')}\n"

                    if fecha:
                        mensaje += f"• Última actualización: {fecha}"

                    return mensaje
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