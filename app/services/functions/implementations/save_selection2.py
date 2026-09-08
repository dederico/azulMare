# Módulo de almacenamiento temporal por usuario y pregunta
user_answers = {}  # key: phone_number, value: dict con {question_number: answer}

def save_user_answer(from_number, question_number, selection_text):
    if from_number not in user_answers:
        user_answers[from_number] = {}
    user_answers[from_number][question_number] = selection_text

def get_user_answer(from_number, question_number):
    return user_answers.get(from_number, {}).get(question_number, "")
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
        selection6 (string): Número (default: 000).
        selection7 (string): Colonia.
        selection8 (string): URL o ruta de la imagen para la pregunta 8.
        images_list (array): Lista de URLs de imágenes.
        descriptions_list (array): Lista de descripciones correspondientes a las imágenes.

    Returns:
        string: Número de folio del reporte.
    """

    import httpx
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
    if selection8 and isinstance(selection8, list):
        # Manejar casos donde selection8 podría contener varias URLs separadas por espacios
        logger.debug(f"Procesando selection8 como lista con {len(selection8)} elementos")
        for url in selection8:
            if isinstance(url, str) and (url.startswith('http') or 'storage.chat2desk.com' in url) and url not in fotos:
                clean_url = url.strip()
                clean_url = urllib.parse.quote(clean_url, safe=':/?&=')
                fotos.append(clean_url)
                logger.debug(f"Añadida URL válida desde selection8 (lista): {clean_url}")
    elif selection8 and isinstance(selection8, str):
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
    asunto_id = selection1 or "984"  # Usar 984 (baches) como valor predeterminado

    # Extraer solo los dígitos si contiene texto
    if not asunto_id.isdigit():
        digits = re.findall(r'\d+', asunto_id)
        if digits:
            asunto_id = digits[0]  # Usar el primer número encontrado
        else:
            asunto_id = "984"  # Valor por defecto si no hay números

    # Asegurar que tenemos valores válidos para todos los campos
    nombre = selection2.strip() if selection2 and selection2.strip() else "Ciudadano"
    descripcion = selection4.strip() if selection4 and selection4.strip() else "Sin descripción"

    # Para la calle, validar que no sea None antes de intentar hacer strip()
    calle = selection5.strip() if selection5 and selection5.strip() else ""

    # El valor predeterminado para selection6 (número) debe ser "100" si está vacío
    numero = selection6.strip() if selection6 and selection6.strip() else "100"
    # Si numero no es un número, intentar extraer dígitos
    if not numero.isdigit():
        nums = re.findall(r'\d+', numero)
        numero = nums[0] if nums else "100"

    # Para el barrio/colonia, validar que no sea None antes de intentar hacer strip()
    colonia = selection7.strip() if selection7 and selection7.strip() else ""

    # Construir la ubicación combinada con verificación de que no queden patrones vacíos
    partes_localizacion = []
    if calle:
        partes_localizacion.append(calle)
        # Solo añadir el número si hay calle
        partes_localizacion.append(numero)

    # Añadir una coma solo si hay calle y colonia
    if partes_localizacion and colonia:
        localizacion = f"{' '.join(partes_localizacion)}, {colonia}"
    elif partes_localizacion:
        # Si no hay colonia, solo usar calle y número
        localizacion = ' '.join(partes_localizacion)
    elif colonia:
        # Si solo hay colonia
        localizacion = colonia
    else:
        # Si no hay nada
        localizacion = "Ubicación no especificada"

    # Verificación final para evitar patrones vacíos
    if localizacion in [", ", " , ", ","]:
        localizacion = "Ubicación no especificada"

    # Asegurar que tenemos al menos una imagen si se proporcionó
    if selection8 and isinstance(selection8, str) and (selection8.startswith('http') or 'storage.chat2desk.com' in selection8) and selection8 not in fotos:
        fotos.append(selection8)

    # Imprimir valores antes de crear el payload para depuración
    logger.debug(f"Valores para el payload:")
    logger.debug(f"  asunto_id: {asunto_id}")
    logger.debug(f"  nombre: {nombre}")
    logger.debug(f"  descripcion: {descripcion}")
    logger.debug(f"  localizacion: {localizacion}")
    logger.debug(f"  fotos: {len(fotos)} imágenes")

    # Preparar el payload con valores verificados
    payload = {
        "reporteId": 0,  # Este parece ser un ID interno, no relacionado con selection1
        "reporteAnonimo": 0 if nombre != "Anónimo" else 1,
        "reporte": descripcion,
        "localizacion": localizacion,
        "nombreReportante": nombre,
        "telefonoReportante": yoga_number,
        "asunto": asunto_id,  # Este es el que debe usar selection1 (tipo de reporte)
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
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=8.0)) as http_client:
            response = await http_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        logger.info(f"POST to {url} successful. Response: {response.status_code} {response.text}")
        
        # Extraer folio: simplemente usamos el texto de la respuesta como el folio
        folio_number = response.text.strip()
        
        # Si está vacío por alguna razón, usar un valor por defecto
        if not folio_number:
            folio_number = "Generado"
            
        # 🧹 NUEVA LÍNEA: PROGRAMAR LIMPIEZA COMPLETA DESPUÉS DE REPORTE EXITOSO
        try:
            import asyncio
            from app.util.logger import logger
            
            async def cleanup_after_manual_report():
                """Limpieza específica para reportes manuales desde save_client_selection2"""
                try:
                    await asyncio.sleep(10)  # Esperar 10 segundos para que el LLM responda
                    
                    logger.critical(f"🧹 [MANUAL CLEANUP] Iniciando limpieza después de reporte manual para {yoga_number}")
                    
                    # Importar las estructuras globales necesarias
                    try:
                        from app.api.original_routes import report_sessions, user_answers, reports_in_progress, report_sessions_lock, reports_lock
                        
                        # Limpiar report_sessions
                        with report_sessions_lock:
                            if yoga_number in report_sessions:
                                del report_sessions[yoga_number]
                                logger.critical(f"🧹 [MANUAL] Eliminado report_sessions[{yoga_number}]")
                        
                        # Limpiar user_answers
                        if yoga_number in user_answers:
                            del user_answers[yoga_number]
                            logger.critical(f"🧹 [MANUAL] Eliminado user_answers[{yoga_number}]")
                        
                        # Limpiar reports_in_progress
                        with reports_lock:
                            if yoga_number in reports_in_progress:
                                del reports_in_progress[yoga_number]
                                logger.critical(f"🧹 [MANUAL] Eliminado reports_in_progress[{yoga_number}]")
                        
                        logger.critical(f"🧹 [MANUAL CLEANUP] ✅ Limpieza manual terminada para {yoga_number}")
                        
                    except ImportError as e:
                        logger.error(f"🧹 [MANUAL CLEANUP ERROR] No se pudieron importar las estructuras: {str(e)}")
                        
                except Exception as e:
                    logger.error(f"🧹 [MANUAL CLEANUP ERROR] Error en limpieza manual: {str(e)}")
            
            # Programar la limpieza asíncrona
            asyncio.create_task(cleanup_after_manual_report())
            logger.critical(f"🧹 [MANUAL] Limpieza programada para {yoga_number} después de reporte manual exitoso")
            
        except Exception as e:
            logger.error(f"🧹 [MANUAL] Error programando limpieza: {str(e)}")
            
        # IMPORTANTE: Devolver una cadena formateada que incluya la palabra "Folio"
        # para evitar problemas con chat2desk
        return f"Folio: {folio_number}"
    
    except Exception as e:
        logger.error(f"Error al enviar el reporte: {e}", exc_info=True)
        return f"Error al procesar la solicitud: {str(e)}"
