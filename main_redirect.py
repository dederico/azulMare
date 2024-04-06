import gspread
from oauth2client.service_account import ServiceAccountCredentials
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
import os

load_dotenv(".env")
#NGROK_URL = os.environ.get("HOSTNAME")
# Configuración de Google Sheets
spreadsheet_key = "1IMK9AbP2-xMlFf9oIxP-JH0KgopRLaUJ4ccTWcGHPIA"
credentials_path = "credentials.json"
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Configuración de Twilio
account_sid = "AC274ae17c4a1dc4f8d1097d5b7f03aef3"
auth_token = "4be617ccc7e365ce45ae0f8504689b4b"
from_phone_number = "+528141701647"
NGROK_URL = os.environ.get("HOSTNAME")
# to_phone_number = '+528181850026'


def authenticate_google_sheets():
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        credentials_path, scope
    )
    gc = gspread.authorize(credentials)
    return gc.open_by_key(spreadsheet_key)


def make_twilio_call(to_phone_number, message):
    client = Client(account_sid, auth_token)
    call = client.calls.create(
        to=to_phone_number,
        from_=from_phone_number,
        url=NGROK_URL,  # Puedes proporcionar un URL con un mensaje grabado o texto a voz
        machine_detection="Enable",
        async_amd="Enable",
        async_amd_status_callback=f"{NGROK_URL}/amd_callback",
    )
    return call.sid

# def make_twilio_call(to_phone_number, host):
#     client = Client(account_sid, auth_token)
#     call = client.calls.create(
#         to=to_phone_number,
#         from_=from_phone_number,
#         url=f"{NGROK_URL}/",  # URL for call handling TwiML
#         machine_detection="Enable",
#         async_amd="Enable",
#         async_amd_status_callback=f"{NGROK_URL}/amd_callback",
#     )
#     return call.sid


def main():
    # Autenticar con Google Sheets
    spreadsheet = authenticate_google_sheets()
    worksheet = spreadsheet.sheet1  # Ajusta según tu hoja de cálculo

    # Obtener datos de la hoja de cálculo
    header_values = worksheet.row_values(
        1
    )  # Obtener los valores de la primera fila (encabezado)
    data = worksheet.get_all_values()  # Obtener todos los valores de la hoja de cálculo

    # Validar que haya datos en la hoja de cálculo
    if not data or len(data) < 2:
        print("La hoja de cálculo está vacía o no hay suficientes datos.")
        return

    # Obtener índices de las columnas
    phone_number_index = (
        header_values.index("phone_number") if "phone_number" in header_values else None
    )
    # Ajusta según tus nombres de columnas en la hoja de cálculo

    # Realizar llamadas telefónicas por cada registro
    for record in data[1:]:  # Excluir la primera fila que es el encabezado
        print(record)
        try:
            if phone_number_index is not None and phone_number_index < len(record):
                phone_number = record[phone_number_index]

                # Puedes personalizar el mensaje según tus necesidades
                message = f"Hola, esta es una llamada desde Twilio. Gracias por usar nuestro servicio."

                # Realizar la llamada
                call_sid = make_twilio_call(phone_number, message)
                if call_sid:
                    print(
                        f"Llamada realizada a {phone_number}. SID de llamada: {call_sid}"
                    )
                else:
                    print(f"Error al realizar la llamada a {phone_number}.")
        except Exception as e:
            print(e)
            pass


if __name__ == "__main__":
    main()
