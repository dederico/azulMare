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
            update_range = f"Sheet1!C{i + 1}"
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


async def save_client_selection(call_sid: str, selection: str):
    """Guardar la seleccion de horario de llamada del cliente.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.
        selection (string): Horario definido por usuario. dd/mm/aa/00:00
    Returns:
        string: Mensaje de confirmacion.
    """
    # Fetch the call
    call = client.calls(call_sid).fetch()

    # Get the caller's phone number
    caller_number = call.to
    await find_row_and_update_selection(caller_number, selection)
    return "Su seleccion ha sido guardada correctamente."
