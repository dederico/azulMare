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
import logging
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import socket

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

# Configuración de logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Credenciales de Google Calendar
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCOPES = ['https://www.googleapis.com/auth/calendar.events','https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE= os.path.join(BASE_DIR, 'functions', 'service_account_credentials.json')
CALENDAR_ID = 'dederico@gmail.com'
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'functions', 'implementations', 'credentials.json')


async def get_credentials():
    """Obtiene las credenciales de usuario válidas del almacenamiento.

    Si no se encuentran credenciales válidas, se completa el flujo OAuth2 para obtener
    las nuevas credenciales.

    Returns:
        Credentials: La credencial obtenida.
    """
    
    # logger.info("Intentando obtener credenciales desde el archivo de cuenta de servicio")
    # return service_account.Credentials.from_service_account_file(
    #     SERVICE_ACCOUNT_FILE, scopes=SCOPES)


    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        logger.info("Credenciales obtenidas exitosamente")
        return creds
    except FileNotFoundError:
        logger.error(f"No se encontró el archivo de credenciales en: {SERVICE_ACCOUNT_FILE}")
        raise
    except Exception as e:
        logger.error(f"Error al obtener credenciales: {e}")
        raise

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
    #             CREDENTIALS_FILE, SCOPES)
    #         port = find_free_port()
    #         creds = flow.run_local_server(port=port)
    #     # Guarda las credenciales para la próxima ejecución
    #     with open(CREDENTIALS_FILE, 'w') as token:
    #         token.write(creds.to_json())
    # return creds



async def create_google_event(start_datetime: str, end_datetime: str, summary="Resumen del evento", location="Monterrey, Mexico", description="Descripción del evento"): #email_address="dederico@gmail.com"):
    """Crea un evento en Google Calendar.
    
    Args:
        start_datetime (string): Fecha y hora de inicio del evento.
        end_datetime (string): Fecha y hora de finalización del evento.
        summary (string): Resumen o título del evento.
        location (string): Ubicación del evento.
        description (string): Descripción del evento.
        
    Returns:
        string: Mensaje de confirmación.
    """
    logger.info("Iniciando creación de evento en Google Calendar")

    try:
        # Parse start and end datetimes
        start_datetime = date_parser.parse(start_datetime)
        end_datetime = date_parser.parse(end_datetime)

        logger.debug(f"Parámetros del evento: start_datetime={start_datetime}, end_datetime={end_datetime}, summary={summary}, location={location}, description={description}")

        creds = await get_credentials()
        logger.info("Credenciales obtenidas, construyendo servicio de Calendar")
        
        service = build('calendar', 'v3', credentials=creds)
        logger.info("Servicio de Calendar construido")

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
            #'attendees': [{'email': email_address}] if email_address else [],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        logger.debug(f"Objeto de evento creado: {event}")

        logger.info("Intentando insertar el evento en el calendario")
        response = service.events().insert(calendarId='primary', body=event).execute()
        logger.info(f"Evento creado exitosamente. ID del evento: {response.get('id')}")
        
        return "Evento añadido exitosamente."
    except Exception as e:
        logger.error(f"Se produjo un error al crear el evento: {e}", exc_info=True)
        return f"Se produjo un error: {e}"
# def main():
#     # Initialize FunctionManager with the create_google_event function
#     function_manager = FunctionManager([create_google_event])

#     # Generate function definition list for openai service
#     function_definitions = function_manager.get_function_definition(service="openai")
#     for function_definition in function_definitions:
#         print(function_definition)