from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
#from .identify import get_customer_identity
#from src.utils import logger
import os
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
HOSTNAME = os.environ.get("HOSTNAME")

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


async def redirect_call(call_sid):
    """Transfer the call to the specified phone number
    Args:
        call_sid (string): call SID
    Returns:
        string: Success Message.
    """
    
    response = VoiceResponse()
    response.say(
        "Excelent! I'll redirect you.",
        voice="Polly.Salli-Neural",
        language="en-US",
    )
    # Add the redirect instructions

    dial = response.dial()
    #"+523335910363",
    dial.number(
        "+528182871484",
        url=f"{HOSTNAME}/handle_redirected_call",
    )
    call = client.calls(call_sid).fetch()

    # Get the caller's phone number
    phone_number = call.to
    # Update the call with the redirect TwiML
    await find_row_and_update_selection(phone_number, "redirected")
    client.calls(call_sid).update(twiml=response.to_xml())
    #logger.info("Redirected successfully.")

    return "Call was redirected successfully"


# Llamada de ejemplo
# call_sid_example = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXX"  # Reemplaza con el SID real de la llamada
# redirect_number_example = "+1234567890"  # Reemplaza con el número al que deseas redirigir la llamada

# result = redirect_call(call_sid_example, redirect_number_example)
# print(result)