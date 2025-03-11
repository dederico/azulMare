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
<div id="canvas_div_pdf" class="canvas_div_pdf" style="margin-top:0px;">
  <img src="assets/media/bg/300a.jpg" width="400px" alt="ENCABEZADO"/>
  <h2>MINUTA DE INICIO DE CASO</h2>
  <p>Por medio de la presente se hace constar la apertura de caso del ciudadano <span class="kt-font-brand">Anónimo</span></p>
  <p>Canal: <span class="kt-font-brand">Presencial</span></p>
  <p>La descripción del caso general se detalla a continuación:</p>
  <ul><li></li></ul>
  <h3>Solución Propuesta</h3>
  <p>Se indica.........</p>
  <img src="assets/media/bg/300b.jpg" width="400px" alt="ENCABEZADO"/>
</div>
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

async def save_client_selection(phone_number: str, selection1: str, selection2: str, selection3: str, selection4: str, selection5: str, selection6: str, selection7: str, selection8: str = None):
    """Guardar la información de las preguntas según las respuestas del cliente.

    Args:
        phone_number (string): El payload completo recibido del webhook.
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
    # Extraer el número de teléfono del payload
    
    if not phone_number:
        logger.error("No se pudo obtener el número de teléfono del cliente.")
        return "Error: No se pudo obtener el número de teléfono"

    logger.info(f"Número del cliente: {phone_number}")

    # Fetch the token
    token = get_token()

    # Save selections for each question if they are not empty
    for i, selection in enumerate([selection1, selection2, selection3, selection4, selection5, selection6, selection7, selection8], start=1):
        if selection:
            await find_row_and_update_selection(phone_number, i, selection)

    # Check if all required fields are filled
    required_fields = [selection1, selection2, selection3, selection4, selection5, selection6, selection7]
    if all(required_fields):
        # Prepare the JSON payload
        payload = {
            "idAsunto": selection1,
            "nombreCiudadano": f"{selection2} {selection3}",
            "numWhastApp": phone_number,
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
                response = requests.get(selection8)
                if response.status_code == 200:
                    # Guardar la imagen localmente
                    image_path = f"temp_image_{phone_number}.jpg"
                    with open(image_path, 'wb') as f:
                        f.write(response.content)
            else:
                # Si es una ruta local, usarla directamente
                image_path = selection8

            # Añadir la imagen al payload si existe
            if image_path:
                with open(image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    payload["imagen"] = encoded_string

                # Limpiar el archivo temporal si se creó
                if image_path.startswith('temp_image_'):
                    os.remove(image_path)

        logger.debug(f"Payload preparado: {payload}")

        # Prepare the headers
        headers = {
            "accept": "text/plain",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Send the JSON payload via POST to the endpoint
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
        return f"Información parcialmente guardada. {filled_fields} de 7 campos requeridos han sido llenados."
