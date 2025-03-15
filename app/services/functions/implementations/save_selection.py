import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from twilio.rest import Client
import os
import re
import requests
import json
import base64
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

# Ejemplo de cómo obtener el token
try:
    token = get_token()
    print(f"Token obtenido: {token}")
except Exception as e:
    print(f"Error al obtener el token: {e}")


# Twilio credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Hardcoded POST endpoint
#POST_ENDPOINT = "https://api-desktop.pau.zone/api-jex/caso/newCasoSin"
#POST_ENDPOINT = "http://api_ac.evolutek.info/api/Reportes/Nuevo/ddf504aa-d6b1-4fa2-bb6d-4ad5d197eea5"
POST_ENDPOINT="https://api.neurocity.solutions/api/solicitud/create"
# Values for the payload
TIPO = "Queja"
CONSEJERIA_ID = "[\"fef66114-d97c-4f25-ad10-fd8af1ebef71\"]"
ESTADO = 155
HTML_CONTENT = """

"""

# Initialize the Twilio client
client = Client(account_sid, auth_token)

# Function to clean phone numbers
def clean_phone_number(phone_number: str) -> str:
    return re.sub(r'\D', '', phone_number)

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
            print(f"Updated row {i + 1} with selection {selection_text} for question {question_number}")
            return

    print("Phone number not found.")

import requests
import base64
import os
from app.util.logger import logger

async def save_client_selection(yoga_number: str, selection1: str, selection2: str, selection3: str, selection4: str, selection5: str, selection6: str, selection7: str, selection8: str = None):
    """Guardar la información de las preguntas según las respuestas del cliente.

    Args:
        yoga_number (string): El número de teléfono del cliente.
        selection1 (string): Respuesta a la pregunta 1.
        selection2 (string): Respuesta a la pregunta 2.
        selection3 (string): Respuesta a la pregunta 3.
        selection4 (string): Respuesta a la pregunta 4.
        selection5 (string): Respuesta a la pregunta 5.
        selection6 (string): Respuesta a la pregunta 6.
        selection7 (string): Respuesta a la pregunta 7.
        selection8 (string, optional): URL o ruta de la imagen para la pregunta 8.

    Returns:
        string: Mensaje de confirmación con el número de folio.
    """
    if not yoga_number:
        logger.error("No se pudo obtener el número de teléfono del cliente.")
        return "Error: No se pudo obtener el número de teléfono"

    logger.info(f"Número del cliente: {yoga_number}")
    
    # Verificar si es una llamada inicial (todos los campos vacíos)
    todos_vacios = all(not field or field.strip() == "" for field in [selection1, selection2, selection3, selection4, selection5, selection6, selection7])
    if todos_vacios:
        logger.debug("Llamada inicial con todos los campos vacíos. No se creará reporte.")
        return "Formulario pendiente de completar"

    try:
        # Fetch the token
        token = get_token()
        logger.debug("Token obtenido correctamente")
    except Exception as e:
        logger.error(f"Error al obtener token: {e}")
        return f"Error al obtener token: {str(e)}"

    # OMITIMOS TEMPORALMENTE LA PARTE DE GOOGLE SHEETS
    logger.debug("SKIPPING Google Sheets update temporarily")

    # Check if all required fields are filled
    required_fields = [selection1, selection2, selection3, selection4, selection5, selection6, selection7]
    campos_con_valor = [field for field in required_fields if field and field.strip()]
    campos_llenos = len(campos_con_valor)
    
    # Si hay muy pocos campos llenos y no son todos vacíos, no generar reporte
    if campos_llenos < 4 and not todos_vacios:
        logger.warning(f"Información insuficiente: {campos_llenos} de 7 campos han sido llenados")
        return f"Información parcialmente guardada. {campos_llenos} de 7 campos requeridos han sido llenados."
    
    # Si tenemos suficientes campos o son todos los necesarios, crear el reporte
    try:
        logger.debug("Preparando payload para Neurocity")
        # Prepare the JSON payload
        payload = {
            "idAsunto": selection1 or "1",  # Valor por defecto
            "nombreCiudadano": f"{selection2 or ''} {selection3 or ''}".strip() or "Anónimo",
            "numWhastApp": yoga_number,
            "anonimo": False,
            "detalleSolicitud": selection4 or "Sin descripción",
            "_lat": "0",
            "_long": "0",
            "_direccionReporte": {
                "calle": selection5 or "No proporcionada",
                "noExt": selection6 or "S/N",
                "colonia": selection7 or "No proporcionada",
                "entreCalles": "Aramberri",
                "referencias": selection4 or "No proporcionadas"
            }
        }

        # Manejar la imagen (selection8) si está presente
        if selection8 and selection8.strip():
            # Código para manejar imágenes si es necesario
            pass

        logger.debug(f"Payload preparado: {payload}")

        # Prepare the headers
        headers = {
            "accept": "text/plain",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Send the JSON payload via POST to the endpoint
        logger.debug(f"Enviando payload a {POST_ENDPOINT}")
        response = requests.post(POST_ENDPOINT, json=payload, headers=headers)
        response.raise_for_status()
        logger.info(f"POST to {POST_ENDPOINT} successful. Response: {response.status_code} {response.text}")
        
        # Extraer el folio de la respuesta
        try:
            response_data = response.json()
            folio = response_data.get("data", {}).get("solicitud", {}).get("folio", "")
            if not folio:
                folio = response.text.strip()
        except:
            folio = response.text.strip()
        
        if campos_llenos < 7:
            return f"Reporte creado con información parcial. Número de folio: {folio}"
        else:
            return f"Selecciones guardadas correctamente. Número de folio: {folio}"
    except Exception as e:
        logger.error(f"Error al enviar a Neurocity: {e}", exc_info=True)
        return f"Error al procesar la solicitud: {str(e)}"
    

