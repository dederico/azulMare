async def save_client_selection2(yoga_number: str, selection1: str, selection2: str, selection3: str,
                               selection4: str, selection5: str, selection6: str, selection7: str, 
                               selection8: str = None, images_list: list = None, descriptions_list: list = None):
    """Guardar la información de las preguntas según las respuestas del cliente.

    Args:
        yoga_number (string): El número de teléfono del cliente.
        selection1 (string): ID numérico del asunto (ej: "984" para baches) o "0" para auto-clasificación.
        selection2 (string): Nombre del cliente.
        selection3 (string): SIEMPRE debe ser una cadena vacía "".
        selection4 (string): Razón del reporte.
        selection5 (string): Calle.
        selection6 (string): Número (default: 100).
        selection7 (string): Colonia.
        selection8 (string, optional): URL o ruta de la imagen para la pregunta 8.
        images_list (list, optional): Lista de URLs de imágenes.
        descriptions_list (list, optional): Lista de descripciones correspondientes a las imágenes.

    Returns:
        string: Número de folio del reporte.
    """

    import requests
    import json
    from app.util.logger import logger
    import re
    import urllib

    logger.critical(f"============= DENTRO DE SAVE CLIENT SELECTION2 =============")
    logger.critical(f"Número: {yoga_number}")
    logger.critical(f"Images list recibida: {images_list}")
    logger.critical(f"Tipo de images_list: {type(images_list)}")

    if images_list:
        logger.critical(f"Longitud de images_list: {len(images_list)}")
        for i, img in enumerate(images_list[:3]):  # Mostrar solo las primeras 3 para evitar logs enormes
            logger.critical(f"  Imagen {i+1}: {img}")

    
    if not yoga_number:
        logger.error("No se pudo obtener el número de teléfono del cliente.")
        return "Error: No se pudo obtener el número de teléfono"

    logger.info(f"Número del cliente: {yoga_number}")
    
    # Verificar si es una llamada inicial (todos los campos vacíos excepto selection3 que siempre es "")
    todos_vacios = all(not field or field.strip() == "" for field in [selection1, selection2, selection4, selection5, selection6, selection7])
    
    # Si hay imágenes, no consideramos que sea una llamada inicial vacía
    if images_list and len(images_list) > 0:
        todos_vacios = False
    if selection8 and isinstance(selection8, str) and (selection8.startswith('http') or 'storage.chat2desk.com' in selection8):
        todos_vacios = False
    
    if todos_vacios:
        logger.debug("Llamada inicial con todos los campos vacíos. No se creará reporte.")
        return "Formulario pendiente de completar"

    # En la parte donde procesas las imágenes
    fotos = []
    if images_list and len(images_list) > 0:
        logger.critical(f"Processing {len(images_list)} images")
        # Filtrar URLs válidas
        for i, img in enumerate(images_list):
            logger.debug(f"Image {i+1}: {img}")
            if isinstance(img, str) and (img.startswith('http') or 'storage.chat2desk.com' in img):
                clean_url = img.strip()
                clean_url = urllib.parse.quote(clean_url, safe=':/?&=')
                fotos.append(clean_url)
                logger.critical(f"  Added valid image URL: {clean_url}")
            else:
                logger.critical(f"  Skipped invalid image URL: {img}")
    else:
        logger.critical("No images provided")

    
    
    # También verificar selection8 para retrocompatibilidad
    if selection8 and isinstance(selection8, str):
        # Manejar casos donde selection8 podría contener varias URLs separadas por espacios
        logger.debug(f"Procesando selection8: {selection8}")
        if ' ' in selection8:
            urls = selection8.split()
            for url in urls:
                if (url.startswith('http') or 'storage.chat2desk.com' in url) and url not in fotos:
                    fotos.append(url)
        # Manejar caso donde selection8 es una única URL
        elif selection8.startswith('http') or 'storage.chat2desk.com' in selection8:
            if selection8 not in fotos:
                fotos.append(selection8)
    
    # Asegurarnos de que el asunto sea solo números
    # Si es "0", se auto-clasificará en process_and_save_report
    asunto_id = selection1 or "0"
    
    # Extraer solo los dígitos si contiene texto
    if not asunto_id.isdigit():
        digits = re.findall(r'\d+', asunto_id)
        if digits:
            asunto_id = digits[0]  # Usar el primer número encontrado
        else:
            asunto_id = "984"  # Valor por defecto si no hay números
    
    # El valor predeterminado para selection6 (número) debe ser "100" si está vacío
    numero = selection6.strip() if selection6 and selection6.strip() else "100"
    
    # Construir la ubicación combinada
    localizacion = f"{selection5 or ''} {numero}, {selection7 or ''}".strip()
    if not localizacion or localizacion in [", ", " , "]:
        localizacion = "Ubicación no especificada"
    
    # Preparar el payload según la nueva estructura de API
    payload = {
        "reporteId": 0,
        "reporteAnonimo": 0 if selection2 and selection2.strip() != "Anónimo" else 1,
        "reporte": selection4 or "Sin descripción",
        "localizacion": localizacion,
        "nombreReportante": selection2 or "Anónimo",
        "telefonoReportante": yoga_number,
        "asunto": asunto_id,  # Usar el valor numérico como ID de asunto
        "tipo": "5",  # Hardcoded según el ejemplo proporcionado
        "fotos": fotos
    }
    
    logger.debug(f"Payload preparado: {json.dumps(payload)}")
    logger.debug(f"Número de fotos en payload: {len(fotos)}")
    # Después de preparar el payload, agregar un log crítico de las imágenes
    logger.critical(f"Número de fotos en payload final: {len(fotos)}")
    logger.critical(f"Fotos en payload: {fotos}")

    try:
        # Configurar el endpoint de la API
        url = "https://ciac.sanpedro.gob.mx/apisag/api/Nuevo/a73a78a5-3a3f-479e-ae11-063c9014f5b7"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Enviar la solicitud
        logger.debug(f"Enviando payload a {url}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        logger.info(f"POST to {url} successful. Response: {response.status_code} {response.text}")
        
        # Extraer folio: simplemente usamos el texto de la respuesta como el folio
        folio_number = response.text.strip()
        
        # Si está vacío por alguna razón, usar un valor por defecto
        if not folio_number:
            folio_number = "Generado"
        
        # IMPORTANTE: Devolver una cadena formateada que incluya la palabra "Folio"
        # para evitar problemas con chat2desk
        return f"Folio: {folio_number}"
    
    except Exception as e:
        logger.error(f"Error al enviar el reporte: {e}", exc_info=True)
        return f"Error al procesar la solicitud: {str(e)}"