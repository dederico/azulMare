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


async def get_customer_discount(call_sid):
    """Obtener el tipo de descuento del CUSTOMER.

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        string: Mensaje de confirmacion.
    """
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

    call = client.calls(call_sid).fetch()

    # Get the caller's phone number
    phone_number = call.to

    # Find the row with the phone number and get the debt amount
    discount_percentage_column = 4  # Assuming debt amount is in the fourth column (0-based index)
    for row in values:
        if len(row) > discount_percentage_column and row[1] == phone_number:
            debt_amount = row[discount_percentage_column]
            return debt_amount

    return "Debt amount not found for the given phone number."

# async def main():
#     result = await get_customer_identity(+573134506576)
#     print(result)


# if __name__ == "__main__":
#     asyncio.run(main())
