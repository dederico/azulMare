import json
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.oauth2 import service_account

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


async def find_by_phone_number(phone_number):
    # Path to your service account key file
    SERVICE_ACCOUNT_FILE = "service_account_credentials.json"

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
    # Find the row with the phone number and get the name
    for row in values:
        if len(row) >= 2 and row[1] == phone_number:
            name = row[0]  # Assuming the name is in the first column
            return name

    return "Name not found for the given phone number."


async def get_customer_identity(call_sid):
    """Obtener la identidad a traves del call_sid

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        string: Mensaje de confirmacion.
    """
    
    call = client.calls(call_sid).fetch()

    # Get the caller's phone number
    phone_number = call.to

    return await find_by_phone_number(phone_number)


# async def main():
#     result = await get_customer_identity(+573134506576)
#     print(result)


# if __name__ == "__main__":
#     asyncio.run(main())
