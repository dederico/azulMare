import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import re
import requests
import json
import base64
import logging
from app.util.logger import logger

def get_token():
    req_url = "https://api.neurocity.solutions/api/auth/authenticate"
    
    headers = {
        "Accept": "text/plain",
        "Content-Type": "application/json"
    }
    
    payload = json.dumps({
        "username": "BotVoice",
        "password": "goikfgVqWiKJ"
    })
    
    response = requests.post(req_url, data=payload, headers=headers)
    
    # Verifica que la solicitud fue exitosa
    if response.status_code == 200:
        # Extrae el access_token de la respuesta
        token = response.json().get('access_token')
        if token:
            return token
        else:
            raise Exception("No se encontró el access_token en la respuesta.")
    else:
        raise Exception(f"Error en la solicitud: {response.status_code}, {response.text}")

# Function to clean phone numbers
def clean_phone_number(phone_number: str) -> str:
    return re.sub(r'\D', '', phone_number)

async def get_selection_value(phone_number, question_number):
    """Obtiene el valor actual de una selección para un número de teléfono específico"""
    try:
        # Lógica similar a find_row_and_update_selection pero solo para lectura
        SERVICE_ACCOUNT_FILE = "credentials.json"
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
        
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=credentials)
        
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1").execute()
        values = result.get("values", [])
        
        cleaned_phone_number = clean_phone_number(phone_number)
        
        for i, row in enumerate(values):
            if i == 0:
                continue
            if len(row) > 1 and clean_phone_number(row[1]) == cleaned_phone_number:
                column_index = 3 + (question_number - 1)
                if len(row) > column_index and row[column_index]:
                    return row[column_index]
                return ""
        
        return ""
    except Exception as e:
        logger.error(f"Error obteniendo selección {question_number} para {phone_number}: {str(e)}")
        return ""
    
async def find_row_and_update_selection(phone_number, question_number, selection_text):
    logger.debug(f"Entering find_row_and_update_selection with phone_number: {phone_number}, question_number: {question_number}, selection_text: {selection_text}")

    # Path to your service account key file
    SERVICE_ACCOUNT_FILE = "credentials.json"

    # Define the scopes
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    try:
        # Authenticate and create the service
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=credentials)
        logger.debug("Successfully authenticated with Google Sheets API")
    except Exception as e:
        logger.error(f"Error authenticating with Google Sheets API: {e}")
        return

    # Read the data from the sheet
    sheet = service.spreadsheets()
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
    
    try:
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1").execute()
        values = result.get("values", [])
        logger.debug(f"Successfully read {len(values)} rows from the sheet")
    except Exception as e:
        logger.error(f"Error reading data from Google Sheet: {str(e)}")
        return
        
    logger.debug(f"Searching for phone number: {phone_number} in the sheet.")
    
    # Clean the phone number
    cleaned_phone_number = clean_phone_number(phone_number)
    logger.debug(f"Cleaned phone number: {cleaned_phone_number}")
    
    # Find the row with the phone number
    for i, row in enumerate(values):
        # Skip header row
        if i == 0:
            continue
        if len(row) > 1 and clean_phone_number(row[1]) == cleaned_phone_number:
            # Update the selection in the appropriate column for the question number
            column_index = 3 + (question_number - 1)  # Assuming questions start from column index 3 (C)
            update_range = f"Sheet1!{chr(64 + column_index)}{i + 1}"
            update_body = {"values": [[selection_text]]}
            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body=update_body,
            ).execute()
            logger.info(f"Updated row {i + 1} with selection {selection_text} for question {question_number}")
            return

    logger.warning(f"Phone number {phone_number} not found in the sheet.")

async def save_client_selection(phone_number: str, selection1: str = "", selection2: str = "", selection3: str = "", selection4: str = "", selection5: str = "", selection6: str = "", selection7: str = "", selection8: str = None):
    """Guardar la información de las preguntas según las respuestas del cliente.

    Args:
        phone_number (string): El número de teléfono del cliente.
        selection1 (string, optional): Valor de tipo de reporte (1-12). Por defecto "".
        selection2 (string, optional): Nombre del cliente. Por defecto "".
        selection3 (string, optional): Apellido del cliente. Por defecto "".
        selection4 (string, optional): Razón del reporte. Por defecto "".
        selection5 (string, optional): Calle del reporte. Por defecto "".
        selection6 (string, optional): Número del reporte. Por defecto "".
        selection7 (string, optional): Colonia del reporte. Por defecto "".
        selection8 (string, optional): URL o ruta de la imagen para la pregunta 8. Por defecto None.

    Returns:
        string: Mensaje de confirmación con el número de folio.
    """
    if not phone_number:
        logger.error("No se pudo obtener el número de teléfono del cliente.")
        return "Error: No se pudo obtener el número de teléfono"

    # Limpiamos el número de teléfono (removemos formato Chat2Desk si existe)
    cleaned_phone_number = clean_phone_number(phone_number)
    logger.info(f"Procesando selecciones para el cliente con número: {cleaned_phone_number}")

    # Validar que todas las selecciones sean strings
    selections = [selection1, selection2, selection3, selection4, selection5, selection6, selection7]
    for i, selection in enumerate(selections):
        if selection is None:
            selections[i] = ""
    
    selection1, selection2, selection3, selection4, selection5, selection6, selection7 = selections
    
    # Fetch the token
    try:
        token = get_token()
        logger.debug("Token de autenticación obtenido correctamente")
    except Exception as e:
        logger.error(f"Error al obtener el token de autenticación: {e}")
        return f"Error: {str(e)}"

    # Save selections for each question if they are not empty
    for i, selection in enumerate([selection1, selection2, selection3, selection4, selection5, selection6, selection7, selection8], start=1):
        if selection:
            await find_row_and_update_selection(cleaned_phone_number, i, selection)

    # Log all values being sent to function
    logger.debug(f"Valores enviados a save_client_selection: phone_number={phone_number}, selection1={selection1}, selection2={selection2}, selection3={selection3}, selection4={selection4}, selection5={selection5}, selection6={selection6}, selection7={selection7}, selection8={selection8}")

    # Check if all required fields are filled
    required_fields = [selection1, selection2, selection3, selection4, selection5, selection6, selection7]
    if all(required_fields):
        # Prepare the JSON payload
        payload = {
            "idAsunto": selection1,
            "nombreCiudadano": f"{selection2} {selection3}",
            "numWhastApp": cleaned_phone_number,
            "anonimo": False,
            "detalleSolicitud": selection4,
            "_lat": "0",
            "_long": "0",
            "_direccionReporte": {
                "calle": selection5,
                "noExt": selection6,
                "colonia": selection7,
                "entreCalles": "Aramberri",
                "referencias": selection4
            }
        }

        # Manejar la imagen (selection8) si está presente
        if selection8:
            image_path = None
            if selection8.startswith('http'):
                # Si es una URL, descargar la imagen
                try:
                    response = requests.get(selection8)
                    if response.status_code == 200:
                        # Guardar la imagen localmente
                        image_path = f"temp_image_{cleaned_phone_number}.jpg"
                        with open(image_path, 'wb') as f:
                            f.write(response.content)
                        logger.debug(f"Imagen descargada correctamente desde {selection8}")
                    else:
                        logger.error(f"Error al descargar imagen: HTTP {response.status_code}")
                except Exception as e:
                    logger.error(f"Error al descargar imagen: {str(e)}")
            else:
                # Si es una ruta local, usarla directamente
                image_path = selection8
                logger.debug(f"Usando imagen local: {image_path}")

            # Añadir la imagen al payload si existe
            if image_path:
                try:
                    with open(image_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        payload["imagen"] = encoded_string
                        logger.debug("Imagen codificada y añadida al payload")

                    # Limpiar el archivo temporal si se creó
                    if image_path.startswith('temp_image_'):
                        os.remove(image_path)
                        logger.debug(f"Archivo temporal {image_path} eliminado")
                except Exception as e:
                    logger.error(f"Error al procesar la imagen: {str(e)}")

        logger.debug(f"Payload preparado: {payload}")

        # Prepare the headers
        headers = {
            "accept": "text/plain",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Send the JSON payload via POST to the endpoint
        POST_ENDPOINT = "https://api.neurocity.solutions/api/solicitud/create"
        try:
            response = requests.post(POST_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()  # Raise an HTTPError on bad status
            logger.info(f"POST to {POST_ENDPOINT} successful. Response: {response.status_code} {response.text}")
            folio = response.text.strip()
            return f"Selecciones guardadas correctamente. Número de folio: {folio}"
        except requests.exceptions.RequestException as e:
            logger.error(f"POST to {POST_ENDPOINT} failed: {e}")
            return f"Error al guardar las selecciones: {str(e)}"
    else:
        # If not all required fields are filled, return a status message
        filled_fields = sum(1 for field in required_fields if field)
        logger.warning(f"Información incompleta: {filled_fields} de 7 campos requeridos han sido llenados")
        return f"Información parcialmente guardada. {filled_fields} de 7 campos requeridos han sido llenados."