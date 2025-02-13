import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from twilio.rest import Client
import os
import re
import requests
import json

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
    # Path to your service account key file
    SERVICE_ACCOUNT_FILE = "credentials.json"

    # Define the scopes
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    # Authenticate and create the service
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=credentials)
    
    # Read the data from the sheet
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1").execute()
    values = result.get("values", [])

    print(f"Searching for phone number: {phone_number} in the sheet.")
    
    # Clean the phone number
    cleaned_phone_number = clean_phone_number(phone_number)
    
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

async def save_client_selection(call_sid: str, selection1: str, selection2: str, selection3: str, selection4: str, selection5: str, selection6: str, selection7: str):
    """Guardar la información de las preguntas segun las respuestas del cliente.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.
        selection1 (string): Respuesta a la pregunta 1.
        selection2 (string): Respuesta a la pregunta 2.
        selection3 (string): Respuesta a la pregunta 3.
        selection4 (string): Respuesta a la pregunta 4.
        selection5 (string): Respuesta a la pregunta 5.
        selection6 (string): Respuesta a la pregunta 6.
        selection7 (string): Respuesta a la pregunta 7.

    Returns:
        string: Mensaje de confirmacion.
    """
    try:
        # Fetch the call
        if call_sid.startswith("CA"):
            call = client.calls(call_sid).fetch()
            caller_number = call.from_formatted
            print(f"Caller number from call: {caller_number}")
        elif call_sid.startswith("SM"):
            # Es un SID de mensaje
            message = client.messages(call_sid).fetch()
            print("ESTE ES EL MENSAJE",message)
            caller_number = message.from_
            print(f"Sender number from message: {caller_number}")
        else:
            print("El SID proporcionado no es válido para llamadas o mensajes.")
    except Exception as e:
        print(f"Error al procesar el SID: {e}")
    # Fetch the token
    token = get_token()
    # Get the caller's phone number
    #caller_number = call.from_formatted  # Use `from_formatted` to get the caller's phone number
    #print(f"Caller number: {caller_number}")

    # Save selections for each question
    await find_row_and_update_selection(caller_number, 1, selection1)
    await find_row_and_update_selection(caller_number, 2, selection2)
    await find_row_and_update_selection(caller_number, 3, selection3)
    await find_row_and_update_selection(caller_number, 4, selection4)
    await find_row_and_update_selection(caller_number, 5, selection5)
    await find_row_and_update_selection(caller_number, 6, selection6)
    await find_row_and_update_selection(caller_number, 7, selection7)


    
    # Prepare the JSON payload
    # payload = {
    #     "fname": selection1,  # Example mapping
    #     "lname": selection2,  # Example mapping
    #     "email": "Anónimo",  # Example hardcoded value
    #     "phone": caller_number,
    #     "titulo": caller_number,  # Example hardcoded value
    #     "descripcion": selection3,  # Example mapping

    #     "consejerias": "[\"fef66114-d97c-4f25-ad10-fd8af1ebef71\"]",
    #     "tipo": TIPO,
    #     "estado": ESTADO,
    #     "htmlContent": HTML_CONTENT,
    #     "canal": "Centralita Voz",  # Example hardcoded value
    #     "idCli": "-1",  # Example hardcoded value
    #     "idConversacion": -1,  # Example hardcoded value
    #     "conector_id": -1  # Example hardcoded value
    # }

    payload = {
        "idAsunto": selection1,
        "nombreCiudadano": selection2 + " " + selection3,
        "numWhastApp": caller_number.replace("whatsapp:+", ""),
        "anonimo": False,
        "detalleSolicitud": selection4,
        "_lat": "0",
        "_long": "0",
        "_direccionReporte": {
            "calle": f"{selection5}",
            "noExt": f"{selection6}",
            "colonia": f"{selection7}",
            "entreCalles": "Aramberri",
            "referencias": f"{selection4}"
        }
    }
    
    print(payload)

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
        print(f"POST to {POST_ENDPOINT} successful. Response: {response.status_code} {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"POST to {POST_ENDPOINT} failed: {e}")
    
    return "Selecciones guardadas correctamente."




