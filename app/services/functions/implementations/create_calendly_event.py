import logging
import os
from dateutil import parser as date_parser
from datetime import timedelta
import requests
from app.services.functions.function_manager import FunctionManager

# Configuración de logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Credenciales de Calendly
CALENDLY_BASE_URL = "https://api.calendly.com/v2"
CALENDLY_TOKEN = "eyJraWQiOiIxY2UxZTEzNjE3ZGNmNzY2YjNjZWJjY2Y4ZGM1YmFmYThhNjVlNjg0MDIzZjdjMzJiZTgzNDliMjM4MDEzNWI0IiwidHlwIjoiUEFUIiwiYWxnIjoiRVMyNTYifQ.eyJpc3MiOiJodHRwczovL2F1dGguY2FsZW5kbHkuY29tIiwiaWF0IjoxNzQwMzY5NDg5LCJqdGkiOiI4ZWY2MzZlNC01OTBmLTRkZTAtYjViZC1mOGMxYzQ4NWEzYTAiLCJ1c2VyX3V1aWQiOiJlNmQ2MGY3NS1mYTYzLTRmMTMtOWFlYi03ODljYWJhZWJiOWYifQ.CjtpsvqF-xIrizaKpWJg7bQtXmUNObZthEg4L9ekfmKJwG8f4gRAixMVMlZV8j1m9TT0Z_mYtJ4lK5fAwhSfbg"

async def create_calendly_event(start_datetime: str, event_type_uri: str, invitee_email: str, name: str = "Invitado"):
    """Crea un evento de Calendly.
    
    Args:
        start_datetime (string): Fecha y hora de inicio del evento.
        event_type_uri (string): Identificador URI del tipo de evento.
        invitee_email (string): Dirección de correo electrónico del invitado.
        name (string, optional): Nombre del invitado. Defaults to "Invitado".
        
    Returns:
        string: Mensaje de confirmación.
    """
    logger.info("Iniciando creación de evento en Calendly")

    try:
        # Parse start datetime
        start_datetime = date_parser.parse(start_datetime)

        logger.debug(f"Parámetros del evento: start_datetime={start_datetime}, "
                     f"event_type_uri={event_type_uri}, invitee_email={invitee_email}, name={name}")

        headers = {
            "Authorization": f"Bearer {CALENDLY_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "start_time": start_datetime.isoformat(),
            "event_type": event_type_uri,
            "invitee": {
                "email": invitee_email,
                "name": name
            },
            "title": "Dr. Appointment",
            "description": "Dr. Appointment"
        }

        logger.info("Intentando crear el evento en Calendly")
        response = requests.post(f"{CALENDLY_BASE_URL}/scheduled_events", headers=headers, json=data)
        response.raise_for_status()

        event_details = response.json()
        logger.info(f"Evento creado exitosamente. ID del evento: {event_details.get('uri')}")
        
        return f"Evento realizado con éxito. ID del evento: {event_details.get('uri')}"
    except requests.exceptions.HTTPError as e:
        logger.error(f"Error HTTP al crear el evento: {e}")
        logger.error(f"Respuesta del servidor: {e.response.text}")
        return f"Se produjo un error al crear el evento: {e}"
    except Exception as e:
        logger.error(f"Error inesperado al crear el evento: {e}", exc_info=True)
        return f"Se produjo un error inesperado: {e}"

# Registrar la función con el FunctionManager
#FunctionManager.register("create_calendly_event", create_calendly_event)