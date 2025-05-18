async def get_report_status(report_id: str):
    """
    Consulta el estado de un reporte por su ID.
    
    Args:
        report_id (string): El ID del reporte a consultar
        
    Returns:
        dict: Información del reporte incluyendo el estado, o None si no se encuentra
    """
    import requests
    import json
    from app.util.logger import logger
    
    # Verificar que el report_id sea válido
    if not report_id or not report_id.strip():
        return {
            "success": False,
            "error": "ID de reporte inválido o vacío",
            "message": "Por favor proporciona un número de folio válido para consultar."
        }
    
    # Limpiar el ID (eliminar letras y caracteres especiales si es necesario)
    import re
    report_id_clean = re.sub(r'[^0-9]', '', report_id)
    
    if not report_id_clean:
        return {
            "success": False,
            "error": "Formato de folio incorrecto",
            "message": "El folio debe contener números. Por favor verifica e intenta nuevamente."
        }
    
    try:
        # Configurar la URL de la API
        api_key = "a73a78a5-3a3f-479e-ae11-063c9014f5b7"  # Clave de API
        url = f"https://ciac.sanpedro.gob.mx/apisag/api/ById/{api_key}/{report_id_clean}"
        
        logger.debug(f"Consultando estado de reporte en: {url}")
        
        # Realizar la solicitud HTTP
        response = requests.get(url, timeout=30)  # Timeout de 10 segundos
        
        # Verificar si la solicitud fue exitosa
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Si la respuesta es una lista, tomar el primer elemento
                if isinstance(data, list) and len(data) > 0:
                    report_data = data[0]
                else:
                    report_data = data
                
                # Extraer la información relevante
                status = report_data.get("estatusReporte", "Desconocido")
                creation_date = report_data.get("fecha", "")
                location = report_data.get("localizacion", "No especificada")
                description = report_data.get("reporte", "Sin descripción")
                
                return {
                    "success": True,
                    "report_id": report_id_clean,
                    "status": status,
                    "creation_date": creation_date,
                    "description": description,
                    "message": f"El reporte con folio {report_id_clean} tiene un estado: {status}."
                }
            except json.JSONDecodeError:
                logger.error(f"Error al decodificar la respuesta JSON: {response.text}")
                return {
                    "success": False,
                    "error": "Error al procesar la respuesta",
                    "message": f"No se pudo procesar la información del reporte con folio {report_id_clean}. Por favor intenta más tarde."
                }
        elif response.status_code == 404:
            return {
                "success": False,
                "error": "Reporte no encontrado",
                "message": f"No se encontró ningún reporte con el folio {report_id_clean}. Por favor verifica el número e intenta nuevamente."
            }
        else:
            logger.error(f"Error en la solicitud: {response.status_code} - {response.text}")
            return {
                "success": False,
                "error": f"Error de servidor: {response.status_code}",
                "message": f"Ocurrió un error al consultar el reporte con folio {report_id_clean}. Por favor intenta más tarde."
            }
    
    except requests.RequestException as e:
        logger.error(f"Error de conexión: {str(e)}")
        return {
            "success": False,
            "error": f"Error de conexión: {str(e)}",
            "message": "No se pudo conectar con el servidor para consultar el estado del reporte. Por favor intenta más tarde."
        }
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return {
            "success": False,
            "error": f"Error inesperado: {str(e)}",
            "message": "Ocurrió un error inesperado al consultar el estado del reporte. Por favor intenta más tarde."
        }