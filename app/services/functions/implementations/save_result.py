import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Initialize the Twilio client
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import os

# Twilio credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Initialize the Twilio client
client = Client(account_sid, auth_token)

async def find_row_and_update_selection(phone_number, selection_text):
    from google.oauth2 import service_account

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

    # Find the row with the phone number
    for i, row in enumerate(values):
        # Skip header row
        if i == 0:
            continue
        if len(row) > 1 and row[1] == phone_number:
            # Update the selection in the found row
            update_range = f"Sheet1!D{i + 1}"
            update_body = {"values": [[selection_text]]}
            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body=update_body,
            ).execute()
            print(f"Updated row {i} with selection: {selection_text}")
            return

    print("Phone number not found.")

async def save_result(call_sid: str, selection: str):
    """Guarda el resultado de la interacción.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        string: Mensaje de confirmacion.
    """
    CLASIFICACIONES = """
    EN BASE A LA INTERACCION CON EL CLIENTE TU DECIDIRAS QUE CLASIFICACION DAREMOS A LA INTERACCION,
    Y UTILIZARAS ESTA LISTA ORDENADA COMO GUÍA:
    1. NUMERO EQUIVOCADO: Numero equivocado, no es la persona que se busca.
    2. BUZON DE VOZ: Buzón de voz.
    3. FALLA TELEFONIA: Falla telefonía.
    4. DELIMITADO 30 SEG: No le interesa el producto, no escucha oferta, te cuelga sin permitir interacción.
    5. CLIENTE MOLESTO: Cliente molesto indica que está cansado de recibir llamadas, puede tener groserías.
    6. NO LE INTERESA PRODUCTO: Escucha oferta pero no le interesa el producto, duración de la llamada más de un minuto, el cliente nunca colgó pero siempre dijo no.
    7. TRAMITE RECIENTE: Ya hizo un tramite igual.
    8. VENTA EXITOSA TRANSFERENCIA: Solo ocupar cuando hubo agenda del cliente o se transfiere agente físico.
    """

    

    # Fetch the call
    call = client.calls(call_sid).fetch()

    # Get the caller's phone number
    caller_number = call.to
    await find_row_and_update_selection(caller_number, selection)
    return CLASIFICACIONES
