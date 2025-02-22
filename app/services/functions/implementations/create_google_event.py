from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os.path
import pytz
from google.auth.transport.requests import Request
#from function_manager import FunctionManager
from dateutil import parser as date_parser
from google.oauth2 import service_account



# Credenciales de Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = './credentials.json'
CALENDAR_ID = 'dederico@gmail.com'

async def get_credentials():
    """Obtiene las credenciales de usuario válidas del almacenamiento.

    Si no se encuentran credenciales válidas, se completa el flujo OAuth2 para obtener
    las nuevas credenciales.

    Returns:
        Credentials: La credencial obtenida.
    """
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return creds

    # creds = None
    # # El archivo token.json almacena los tokens de acceso y de actualización del usuario, y se
    # # crea automáticamente cuando se completa el flujo de autorización por primera vez.
    # if os.path.exists('token.json'):
    #     creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # # Si no hay credenciales (válidas) disponibles, se permite al usuario iniciar sesión.
    # if not creds or not creds.valid:
    #     if creds and creds.expired and creds.refresh_token:
    #         creds.refresh(Request())
    #     else:
    #         flow = InstalledAppFlow.from_client_secrets_file(
    #             'credentials.json', SCOPES)
    #         creds = flow.run_local_server(port=0)
    #     # Guarda las credenciales para la próxima ejecución
    #     with open('token.json', 'w') as token:
    #         token.write(creds.to_json())
    # return creds

async def create_google_event(start_datetime: str, end_datetime: str, summary="Resumen del evento", location="Monterrey, Mexico", description="Descripción del evento", email_address="dederico@gmail.com"):
    """Crea un evento en Google Calendar.
    
    Args:
        start_datetime (string): Fecha y hora de inicio del evento.
        end_datetime (string): Fecha y hora de finalización del evento.
        summary (string): Resumen o título del evento.
        location (string): Ubicación del evento.
        description (string): Descripción del evento.
        email_address (string): Dirección de correo electrónico del asistente.
        
    Returns:
        string: Mensaje de confirmación.
    """
    # Parse start and end datetimes
    start_datetime = date_parser.parse(start_datetime)
    end_datetime = date_parser.parse(end_datetime)

    print("Creating Google Calendar event with the following parameters:")
    print(f"start_datetime: {start_datetime}")
    print(f"end_datetime: {end_datetime}")
    print(f"summary: {summary}")
    print(f"location: {location}")
    print(f"description: {description}")
    print(f"email_address: {email_address}")

    creds = await get_credentials()
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                'timeZone': 'America/Mexico_City',
            },
            'end': {
                'dateTime': end_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                'timeZone': 'America/Mexico_City',
            },
            'attendees': [{'email': email_address}] if email_address else [],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        print("Event object:", event)
        service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return "Evento añadido exitosamente."
    except Exception as e:
        return f"Se produjo un error: {e}"
# def main():
#     # Initialize FunctionManager with the create_google_event function
#     function_manager = FunctionManager([create_google_event])

#     # Generate function definition list for openai service
#     function_definitions = function_manager.get_function_definition(service="openai")
#     for function_definition in function_definitions:
#         print(function_definition)