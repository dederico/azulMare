import base64
import aiohttp
import logging
import urllib.parse
import os
import json
from io import StringIO
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytz
from io import BytesIO
import requests
from openai import OpenAI
import asyncio
from contextlib import asynccontextmanager
import httpx
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.util.database import LocalStorage
from app.models.Config import Config
from app.models.Message import Message
from app.services.llm.openai_service import OpenAIService
from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions
from app.util.logger import logger
from datetime import datetime
import pytz
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
import traceback
from app.services.llm.llm_service import LLMService
import psycopg2


load_dotenv(override=True)
from fastapi import APIRouter, Request, Response, WebSocket, HTTPException, FastAPI
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.api.websocket_handler import WebSocketHandler
from app.core.orchestrator import Orchestrator
from app.services.stt.deepgram_service import DeepgramService
from app.services.stt.amazon_service import AmazonTranscribeService
from app.services.llm.openai_service import OpenAIService
from app.services.tts.eleven_service import ElevenTTSService
from app.services.tts.polly_service import AmazonTTSService
from app.services.functions.function_registry import registered_functions
from app.services.llm.config.system import system_message
from app.services.functions.function_manager import FunctionManager
from app.services.functions.implementations.geocoding import latlong_to_address

from twilio.rest import Client
from urllib.parse import parse_qs
from datetime import datetime
from copy import deepcopy
from app.util.logger import logger, get_thread_log_handler, cleanup_call_logger
from app.models.Call import Call
from app.models.Message import Message
from app.models.Config import Config
from app.util.factory import Hooks
from app.util.database import LocalStorage
from app.services.functions.implementations.save_selection import save_client_selection, find_row_and_update_selection
from app.services.functions.implementations.identify import get_customer_identity
from app.services.functions.implementations.date import get_current_date
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from app.services.stt.stt_service import STTService
from app.services.stt.media_transcriber import TranscribeOGG
from twilio.base.exceptions import TwilioRestException
import threading
import asyncio
from app.services.functions.implementations.transfer_message_event import transfer_to_group


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")

# Diccionario para almacenar reportes en progreso
report_sessions = {}  # key: phone_number, value: {images: [], image_descriptions: [], location: str, timestamp: datetime}
reports_lock = threading.Lock()
reports_in_progress = {}
transferred_numbers = {}  # key: phone_number, value: expiration_timestamp
transfer_timeout = 15 * 60  # 15 minutes in seconds

# async def process_and_save_report(from_number, location, images=None, descriptions=None):
#     """
#     Función centralizada para procesar y guardar reportes.
#     Evita múltiples llamadas a save_client_selection para el mismo número.
#     """
#     # Initialize empty lists for images and descriptions if None
#     images = images or []
#     descriptions = descriptions or []
    
#     # Verificar si ya hay un reporte en proceso para este número
#     with reports_lock:
#         if from_number in reports_in_progress and reports_in_progress[from_number]:
#             logger.warning(f"Ya hay un reporte en proceso para {from_number}, ignorando solicitud adicional")
#             return "en_proceso"
        
#         # Marcar que estamos procesando un reporte para este número
#         reports_in_progress[from_number] = True
    
#     try:
#         # Intentar crear el reporte
#         folio = await save_client_selection(
#             from_number, 
#             location,
#             "", "", "", "", "", "",
#             None,
#             images,
#             descriptions
#         )
        
#         # Si llegamos aquí, el reporte se creó con éxito
#         return folio
#     except Exception as e:
#         logger.error(f"Error al procesar reporte para {from_number}: {str(e)}")
#         return f"error: {str(e)}"
#     finally:
#         # Siempre liberar el estado "en proceso"
#         with reports_lock:
#             if from_number in reports_in_progress:
#                 reports_in_progress[from_number] = False

async def manage_message_history(db, number, max_messages=20):
    """
    Mantiene solo los últimos max_messages mensajes para un número dado
    """
    try:
        # Contar cuántos mensajes tiene este número
        conn = psycopg2.connect(dbname=db.dbName, user=db.user, password=db.password, host=db.host, port=db.port)
        cursor = conn.cursor()
        
        # Contar mensajes
        cursor.execute("SELECT COUNT(*) FROM messages WHERE number = %s", [number])
        count = cursor.fetchone()[0]
        
        # Si hay más mensajes que el máximo permitido, eliminar los más antiguos
        if count > max_messages:
            # Obtener los IDs de los mensajes más antiguos que exceden el límite
            cursor.execute("""
                DELETE FROM messages 
                WHERE id IN (
                    SELECT id FROM messages 
                    WHERE number = %s 
                    ORDER BY time ASC 
                    LIMIT %s
                )
            """, [number, count - max_messages])
            
            deleted_count = cursor.rowcount
            logger.debug(f"Se eliminaron {deleted_count} mensajes antiguos para mantener el límite de {max_messages} para {number}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error al gestionar historial de mensajes: {str(e)}")

async def check_report_timeouts():
    """Revisa sesiones de reporte que han estado inactivas por más de 3 minutos y las finaliza."""
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        now = datetime.now(pytz.timezone('America/Mexico_City'))
        
        for number, session in list(report_sessions.items()):
            elapsed = (now - session["timestamp"]).total_seconds()
            if elapsed > 180:  # 3 minutos de inactividad
                # Solo finalizar si hay imágenes
                if session["images"]:
                    # Usar la función centralizada para procesar el reporte
                    location = session["location"] or "ubicación no especificada"
                    result = await process_and_save_report(
                        number, 
                        location,
                        session["images"],
                        session["image_descriptions"]
                    )
                    
                    if result != "en_proceso" and not result.startswith("error:"):
                        logger.info(f"Reporte finalizado automáticamente por timeout: {result}")
                    
                # Limpiar la sesión independientemente del resultado
                del report_sessions[number]

router = APIRouter()
# Historial en memoria para una conversación dinámica
user_histories = {}

@router.post("/")
async def post(request: Request):
    response = VoiceResponse()
    host = request.headers.get("host")
    connect = Connect()
    connect.stream(url=f"wss://{host}/stream")
    response.append(connect)
    text = response.to_xml()
    logger.debug(text)
    return Response(content=text, media_type="text/xml")


@router.websocket("/stream")
async def websocket_endpoint(ws: WebSocket):
    db = LocalStorage()
    config = { conf.name: conf.getval() for conf in db.GetAll(Config) }

    logHandler = get_thread_log_handler(config.get("rawLogs", 10))

    logger.info("Got new INCOMING_CALL")

    websocket_handler = WebSocketHandler(ws)
    await websocket_handler.connect()

    # Set up Deepgram as the Speech-to-Text (STT) Model
    #stt_service = DeepgramService(DEEPGRAM_API_KEY)


    # Set up Amazon Transcribe as the Speech-to-Text (STT) Model.
    logger.debug("Setting up transcription service")
    stt_service = AmazonTranscribeService(
        region="us-east-1",
        sample_rate=8000,
        enhanced=False,
        language=config["language"]
    )

    function_manager = FunctionManager(registered_functions)

    # Get the current date and time
    now = datetime.now()
    callDirection = "Inbound"
    call = db.Search(Call(callUid = websocket_handler.call_sid), True)
    if call:
        callDirection = "Outbound"
        call.callStatus = "IN_PROGRESS"
        db.Update(call)
    else:
        call = Call(
            callTime = now.strftime("%Y-%m-%d %H:%M:%S"),
            callSource = "Twillio",
            callType = "IP",
            callDirection = "IN_COMING",
            callStatus = "IN_PROGRESS",
            callNumber = "Not Available",
            callUid = websocket_handler.call_sid
        )
        call = db.Insert(call)

    mexico_tz = pytz.timezone('America/Mexico_City')
    current_datetime = datetime.now(mexico_tz)
    print(f"Hora original (MX): {current_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
    date_string = current_datetime.strftime("%Y-%m-%d")
    hour = current_datetime.strftime("%I:%M:%S %p")
    print(f"\nRESULTADO FINAL -> Fecha: {date_string}, Hora: {hour}")

    # Get call SID and customer identity
    call_sid = websocket_handler.call_sid
    customer_identity = await get_customer_identity(call_sid)
    call.callerName = customer_identity

    selection1 = await find_row_and_update_selection(call.callNumber, 1)
    selection2 = await find_row_and_update_selection(call.callNumber, 2)
    selection3 = await find_row_and_update_selection(call.callNumber, 3)
    selection4 = await find_row_and_update_selection(call.callNumber, 4)
    selection5 = await find_row_and_update_selection(call.callNumber, 5)
    selection6 = await find_row_and_update_selection(call.callNumber, 6)
    selection7 = await find_row_and_update_selection(call.callNumber, 7)

    #folio = await save_client_selection(call_sid, selection1, selection2, selection3, selection4, selection5, selection6, selection7)

    logger.debug("Initializing LLM service for the new call")
    llm_service = OpenAIService(
        config=config,
        api_key=OPENAI_API_KEY,
        system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date2=date_string, now=hour, folio="folio"),
        function_manager=function_manager
    )

    # tts_service = ElevenTTSService(
    #     api_key=ELEVENLABS_API_KEY,
    #     voice_id=VOICE_ID,
    #     similarity_boost=0.6,
    #     stability=0.7,
    #     stream_results=True,
    # )

    logger.debug("Initializing TTS engine for call")
    tts_service = AmazonTTSService(
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        stream_results=False,
        language=config["language"]
    )

    logger.debug("Initializing orchestrator for the call")
    orchestrator = Orchestrator(
        config=config,
        websocket_handler=websocket_handler,
        stt_service=stt_service,
        llm_service=llm_service,
        tts_service=tts_service,
    )

    logger.debug("Starting a conversation with caller")
    stats = await orchestrator.process_audio_stream()

    # Sync the call record in case of AMD detection event was triggered
    call = db.Search(Call(callUid = websocket_handler.call_sid), True)
    call.callLogs = logHandler.stream.getvalue()

    if config.get(f"saveScript{callDirection}", False):
        call.callScript = json.dumps(stats['Script'])
    
    if config.get(f"recordCalls{callDirection}", False):
        call.callPlayback = json.dumps(websocket_handler.audio_sequence)
    
    if call.callStatus != "AMD":
        # (VERY IMPORTANT) only update status if AMD is not detected
        call.callStatus = stats['Status']

    call.callDuration = (datetime.now() - now).seconds
    db.Update(call)
    
    hooks = Hooks()
    for hook in hooks.Get(True):
        if hook["type"] == "POST_CALL":
            logger.debug("Hook found for call executing function " + hook["name"])
            hook["function"](call, config)

    cleanup_call_logger()

# Diccionario global para almacenar las sesiones de WhatsApp.
# En vez de user_histories, usamos user_sessions para incluir la marca de última actividad.
user_sessions = {}  # key: from_number, value: WhatsAppSession

# Tiempo de inactividad (en segundos) antes de desconectar la sesión (5 minutos)
INACTIVITY_THRESHOLD = 2 * 60

class WhatsAppSession:
    def __init__(self, history):
        self.history = history
        self.last_active = datetime.now(pytz.timezone('America/Mexico_City'))
    
    def update_activity(self):
        self.last_active = datetime.now(pytz.timezone('America/Mexico_City'))

async def check_inactivity():
    """
    Tarea en background que revisa cada minuto las sesiones activas.
    Si alguna sesión ha estado inactiva más de 5 minutos, se envía un mensaje
    de alerta por Chat2Desk, elimina los mensajes de la base de datos y elimina la sesión.
    """
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        now = datetime.now(pytz.timezone('America/Mexico_City'))
        db = LocalStorage()
        
        for number, session in list(user_sessions.items()):
            elapsed = (now - session.last_active).total_seconds()
            if elapsed > INACTIVITY_THRESHOLD:
                try:
                    # Notificar al usuario usando Chat2Desk
                    api_token = os.getenv("CHAT2DESK_API_TOKEN")
                    chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                    
                    # Buscar cliente en Chat2Desk para obtener client_id
                    search_url = "https://api.chat2desk.com.mx/v1/clients"
                    params = {"phone": number}
                    
                    headers = {
                        "Authorization": api_token,
                        "Content-Type": "application/json"
                    }
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.get(search_url, params=params, headers=headers)
                    
                    if response.status_code == 200:
                        client_data = response.json()
                        if client_data.get("status") == "success" and client_data.get("data"):
                            client_id = client_data["data"][0]["id"]
                            channel_id = 43347  # Canal fijo para WhatsApp
                            
                            # Enviar mensaje de desconexión
                            message_data = {
                                "client_id": client_id,
                                "channel_id": channel_id,
                                "transport": "wa_direct",
                                "text": "Se ha desconectado la sesión por inactividad. Para iniciar una nueva conversación, envía un mensaje."
                            }
                            
                            async with httpx.AsyncClient() as client:
                                await client.post(chat2desk_url, json=message_data, headers=headers)
                    
                    # Eliminar todos los mensajes de este número de la base de datos
                    conn = psycopg2.connect(dbname=db.dbName, user=db.user, password=db.password, host=db.host, port=db.port)
                    cursor = conn.cursor()
                    
                    # SQL directo para eliminar mensajes por número
                    cursor.execute("DELETE FROM messages WHERE number = %s", [number])
                    count = cursor.rowcount
                    
                    conn.commit()
                    conn.close()
                    
                    logger.debug(f"Se eliminaron {count} mensajes para el número {number} por inactividad.")
                    
                    # Eliminar la sesión
                    del user_sessions[number]
                    # Eliminar también cualquier reporte en progreso
                    if number in report_sessions:
                        del report_sessions[number]
                    logger.debug(f"Sesión de {number} desconectada por inactividad.")
                except Exception as e:
                    logger.error(f"Error enviando mensaje de desconexión para {number}: {str(e)}")
                    # Aún intentamos eliminar la sesión incluso si falló el envío del mensaje
                    if number in user_sessions:
                        del user_sessions[number]
                    if number in report_sessions:
                        del report_sessions[number]

# # Aquí va la nueva función centralizada
# async def process_and_save_report(from_number, location, images, descriptions):
#     """
#     Función centralizada para procesar y guardar reportes.
#     Evita múltiples llamadas a save_client_selection para el mismo número.
#     """
#     # Verificar si ya hay un reporte en proceso para este número
#     with reports_lock:
#         if from_number in reports_in_progress and reports_in_progress[from_number]:
#             logger.warning(f"Ya hay un reporte en proceso para {from_number}, ignorando solicitud adicional")
#             return "en_proceso"
        
#         # Marcar que estamos procesando un reporte para este número
#         reports_in_progress[from_number] = True
    
#     try:
#         # Intentar crear el reporte
#         folio = await save_client_selection(
#             from_number, 
#             location,
#             "", "", "", "", "", "",
#             None,
#             images,
#             descriptions
#         )
        
#         # Si llegamos aquí, el reporte se creó con éxito
#         return folio
#     except Exception as e:
#         logger.error(f"Error al procesar reporte para {from_number}: {str(e)}")
#         return f"error: {str(e)}"
#     finally:
#         # Siempre liberar el estado "en proceso"
#         with reports_lock:
#             if from_number in reports_in_progress:
#                 reports_in_progress[from_number] = False

finalized_report_numbers = set()

# Modify the process_and_save_report function
async def process_and_save_report(from_number, location, images, descriptions):
    """
    Función centralizada para procesar y guardar reportes.
    Evita múltiples llamadas a save_client_selection para el mismo número.
    """
    # EXTRA CHECK: Verify if this number has recently finalized a report
    if from_number in finalized_report_numbers:
        logger.warning(f"Reporte ya finalizado recientemente para {from_number}, ignorando solicitud duplicada")
        return "ya_finalizado"
    
    # Verificar si ya hay un reporte en proceso para este número
    with reports_lock:
        if from_number in reports_in_progress and reports_in_progress[from_number]:
            logger.warning(f"Ya hay un reporte en proceso para {from_number}, ignorando solicitud adicional")
            return "en_proceso"
        
        # Marcar que estamos procesando un reporte para este número
        reports_in_progress[from_number] = True
    
    try:
        # Check if there are actually images to process
        if not images or len(images) == 0:
            logger.warning(f"Intento de finalizar reporte sin imágenes para {from_number}")
            return "sin_imagenes"
            
        # Intentar crear el reporte
        folio = await save_client_selection(
            from_number, 
            location,
            "", "", "", "", "", "",
            None,
            images,
            descriptions
        )
        
        # Add this number to the finalized set with a timeout removal
        finalized_report_numbers.add(from_number)
        
        # Schedule removal from finalized set after 5 minutes
        asyncio.create_task(remove_from_finalized(from_number, 300))  # 300 seconds = 5 minutes
        
        # Si llegamos aquí, el reporte se creó con éxito
        return folio
    except Exception as e:
        logger.error(f"Error al procesar reporte para {from_number}: {str(e)}")
        return f"error: {str(e)}"
    finally:
        # Siempre liberar el estado "en proceso"
        with reports_lock:
            if from_number in reports_in_progress:
                reports_in_progress[from_number] = False

# Helper function to remove a number from the finalized set after a delay
async def remove_from_finalized(number, delay_seconds):
    await asyncio.sleep(delay_seconds)
    if number in finalized_report_numbers:
        finalized_report_numbers.remove(number)
        logger.debug(f"Número {number} removido de la lista de reportes finalizados después de {delay_seconds} segundos")

async def remove_from_transferred(number, delay_seconds):
    await asyncio.sleep(delay_seconds)
    if number in transferred_numbers:
        transferred_numbers.remove(number)
        logger.debug(f"Bot re-enabled for {number} after {delay_seconds} seconds")
# ------------------------------
# Función de ciclo de vida (lifespan)
# ------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: se lanzan las tareas de verificación
    asyncio.create_task(check_inactivity())
    asyncio.create_task(check_report_timeouts())
    yield
    # Shutdown: se puede agregar lógica de limpieza si se requiere
app = FastAPI(lifespan=lifespan)

router = APIRouter()


# Add this at the module level (outside of the function)
processed_message_ids = set()

@router.post("/whatsapp")
async def whatsapp(request: Request):
    logger.debug("Iniciando procesamiento del mensaje de WhatsApp.")
    # Configuración de base de datos y demás servicios
    db = LocalStorage()
    args = request.query_params
    config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
    function_manager = FunctionManager(registered_functions)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        payload = await request.json()  # Recibimos el payload como JSON
        print(f"Payload recibido: {payload}")
        
        # IMPORTANTE: Verificar si es un mensaje de un cliente o una respuesta del sistema
        message_type = payload.get('type', '')
        uid = payload.get('message_id')
        
        # Solo procesar mensajes que vienen del cliente (ignorar webhooks de mensajes enviados por el bot)
        if message_type != 'from_client':
            logger.debug(f"Ignorando mensaje con type={message_type} que no es from_client")
            return JSONResponse(content={"status": True, "message": "Mensaje del sistema ignorado"})
        
        # Verificar si este mensaje ya ha sido procesado (deduplicación)
        if uid in processed_message_ids:
            logger.debug(f"Ignorando mensaje duplicado con id={uid}")
            return JSONResponse(content={"status": True, "message": "Mensaje duplicado ignorado"})
        
        # Marcar este mensaje como procesado
        processed_message_ids.add(uid)
        
        # Limitar el tamaño del conjunto para evitar crecimiento indefinido
        if len(processed_message_ids) > 1000:
            # Eliminar los elementos más antiguos (esto es simplificado, podría usar una cola)
            processed_message_ids.clear()
            processed_message_ids.add(uid)
        
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        channel_id = payload.get('channel_id')
        client_id = payload.get('client_id')

        # ADD THIS CHECK RIGHT HERE - AFTER extracting from_number but BEFORE any message processing
        current_time = datetime.now().timestamp()
        if from_number in transferred_numbers and current_time < transferred_numbers[from_number]:
            # This number has been transferred to a human agent and the transfer hasn't expired
            logger.info(f"Ignoring message from {from_number} as it's being handled by a human agent (expires in {int(transferred_numbers[from_number] - current_time)} seconds)")
            return JSONResponse(content={"status": True, "message": "Message ignored - conversation transferred to human agent"})
        elif from_number in transferred_numbers:
            # Transfer has expired, remove it from the dictionary
            logger.info(f"Transfer for {from_number} has expired, bot is now responding again")
            del transferred_numbers[from_number]
        
        logger.debug(f"Datos recibidos: chat_id={chat_id}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, message_type={message_type}, uid={uid}")
        


        # Variables para ubicación, imagen y audio
        address = None
        latitude, longitude = None, None
        photo_url = None
        audio_url = None
        image_description = None

        # Verificación del tipo de contenido en el mensaje
        if payload.get("coordinates"):
            # Procesamiento de ubicación
            coords = payload.get("coordinates")
            logger.debug(f"Formato de coordenadas recibidas: {coords}")
            
            # Manejar tanto formato con coma como con espacio
            if isinstance(coords, str):
                if "," in coords:
                    latitude, longitude = coords.split(",")
                elif " " in coords:
                    longitude, latitude = coords.split(" ")  # Nota: en tu payload, primero viene la longitud
                else:
                    logger.error(f"Formato de coordenadas desconocido: {coords}")
                    latitude, longitude = None, None
                    
                if latitude and longitude:
                    try:
                        # Asegurarse que las coordenadas son números flotantes
                        latitude = float(latitude.strip())
                        longitude = float(longitude.strip())
                        
                        # Convertir la latitud y longitud a dirección
                        address = await latlong_to_address(latitude, longitude)
                        body = f"Ubicación recibida: {address}\nLatitud: {latitude}, Longitud: {longitude}"
                        
                        # Si hay un reporte en progreso, actualizar la ubicación
                        if from_number in report_sessions:
                            report_sessions[from_number]["location"] = address
                            report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                    except Exception as e:
                        logger.error(f"Error al convertir coordenadas a dirección: {str(e)}")
                        body = f"Ubicación recibida: Latitud {latitude}, Longitud {longitude}"
                    
                    logger.debug(f"Mensaje con ubicación: latitude={latitude}, longitude={longitude}, address={address if 'address' in locals() else 'No disponible'}")

        elif payload.get("audio"):
            # Procesamiento de audio
            audio_url = payload.get("audio")
            body = TranscribeOGG(audio_url, config["language"])
            logger.debug(f"Audio transcrito: {body}")

        elif payload.get("photo"):
        # Procesamiento de imagen
            photo_url = payload.get("photo")
            if photo_url:
                try:
                    # Descargar la imagen 
                    response = requests.get(photo_url)
                    image_content = BytesIO(response.content)
                    
                    # Analizar la imagen
                    image_analysis = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Describe esta imagen en detalle."},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64.b64encode(image_content.getvalue()).decode('utf-8')}",
                                        },
                                    },
                                ],
                            }
                        ],
                        max_tokens=300,
                    )
                    
                    # Obtener la descripción de la imagen
                    image_description = image_analysis.choices[0].message.content
                    
                    # Almacenar en la sesión de reporte
                    if from_number not in report_sessions:
                        report_sessions[from_number] = {
                            "images": [],
                            "image_descriptions": [],
                            "location": None,
                            "timestamp": datetime.now(pytz.timezone('America/Mexico_City')),
                            "report_pending": True
                        }
                    
                    # Añadir esta imagen al reporte en progreso
                    report_sessions[from_number]["images"].append(photo_url)
                    report_sessions[from_number]["image_descriptions"].append(image_description)
                    report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                    
                    num_images = len(report_sessions[from_number]["images"])

                    if num_images == 1:
                        body = f"Imagen recibida y guardada para tu reporte. Descripción: {image_description}\n\nPuedes enviar más imágenes o indicarme la ubicación del problema. NO ESTOY CREANDO NINGÚN REPORTE TODAVÍA. Cuando quieras finalizar tu reporte, dime claramente 'Crear reporte'."
                    else:
                        body = f"Imagen adicional recibida ({num_images} en total). Descripción: {image_description}\n\nPuedes seguir enviando imágenes. NO ESTOY CREANDO NINGÚN REPORTE TODAVÍA. Cuando estés listo, dime claramente 'Crear reporte'."
                    
                    logger.debug(f"Imagen añadida al reporte en progreso para {from_number}. Total: {num_images}")
                    
                except requests.RequestException as e:
                    logger.error(f"Error al descargar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero no se pudo descargar. Por favor, intenta enviarla de nuevo."
                except Exception as e:
                    logger.error(f"Error al analizar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero hubo un problema al analizarla. El equipo técnico ha sido notificado."
            else:
                body = "Se recibió una notificación de imagen, pero no se encontró la URL de la imagen."
                logger.warning("No se pudo obtener la URL de la imagen del formulario de datos.")
            
        # Now let's fix the report finalization check in the WhatsApp endpoint
        elif body and from_number in report_sessions and report_sessions[from_number]["images"]:
            # El usuario ya ha enviado imágenes, este texto podría ser información del reporte
            is_location = any(keyword in body.lower() for keyword in ["ubicación", "dirección", "calle", "avenida", "colonia", "avenue", "numero", "número"])
            is_finalization = any(keyword in body.lower() for keyword in [
                "listo", "ya terminé", "he terminado", "terminé", "estoy listo", 
                "generar reporte", "crear reporte", "hacer reporte", 
                "levantar reporte", "reportar", "ingresar"
            ])
            
            # Check if this message is likely from the bot (by checking recent history)
            is_likely_bot_message = False
            if from_number in user_sessions:
                # Check the last few messages in the conversation history
                recent_messages = user_sessions[from_number].history.messages[-3:]  # Last 3 messages
                for msg in recent_messages:
                    if isinstance(msg, AIMessage) and body in msg.content:
                        # If this message content appears in a recent bot message, flag it
                        is_likely_bot_message = True
                        logger.warning(f"Possible bot-generated message detected: '{body[:30]}...'")
                        break
            
            if is_likely_bot_message:
                # Skip processing if this appears to be from the bot
                return JSONResponse(content={"status": True, "message": "Mensaje duplicado ignorado"})
            
            if is_location:
                # Es información de ubicación
                report_sessions[from_number]["location"] = body
                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                body = f"Ubicación registrada: {body}. Para finalizar tu reporte con las imágenes que has enviado, avísame cuando estés listo."
            elif is_finalization:
                # El usuario quiere finalizar el reporte
                images = report_sessions[from_number]["images"]
                descriptions = report_sessions[from_number]["image_descriptions"]
                # Use the location stored in the report session or the current message as fallback
                user_location = report_sessions[from_number]["location"] or body or "ubicación no especificada"
                
                # Usar la función centralizada para procesar el reporte
                result = await process_and_save_report(from_number, user_location, images, descriptions)
                
                if result == "en_proceso":
                    body = "Tu reporte ya está siendo procesado. Por favor, espera unos momentos."
                elif result == "ya_finalizado":
                    body = "Tu reporte ya fue finalizado hace unos momentos. Por favor, espera mientras se procesa."
                elif result.startswith("error:"):
                    body = f"Lo siento, hubo un error al finalizar tu reporte: {result[6:]}. Por favor, intenta nuevamente."
                else:
                    # El reporte se creó exitosamente
                    folio = result
                    # Limpiar la sesión de reporte después de finalizar
                    if from_number in report_sessions:
                        del report_sessions[from_number]
                    
                    # Importante: Construir un mensaje informativo que *NO* requiera acción adicional del usuario
                    image_text = f"con {len(images)} imágenes " if images else ""
                    body = f"Tu reporte ha sido generado con éxito. El número de folio para tu reporte es {folio}. Tu reporte {image_text}ha sido enviado al sistema. Agradecemos mucho tu colaboración. ¿Hay algo más en lo que pueda asistirte hoy?"
                    
                    # Crear y guardar un mensaje de sistema explicando lo que ocurrió
                    img_count = f"que incluye {len(images)} imágenes " if images else ""
                    system_notification = Message(
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        senderName="System",
                        message=f"[SISTEMA: Se generó el reporte con folio {folio} {img_count}de la ubicación '{user_location}'. El reporte ha sido enviado al sistema.]",
                        number=from_number,
                        uid=f"system-{uid}",
                        direction="system",
                        mtype="text",
                        source="whatsapp"
                    )
                    db.Insert(system_notification)
                    
    # Continuar con el procesamiento normal
    except KeyError as e:
        logger.error(f"Falta el parámetro requerido: {e}")
        return JSONResponse(content={"error": f"Falta el parámetro {str(e)}"}, status_code=400)
    except Exception as e:
        logger.error(f"Error al procesar el payload: {str(e)}")
        return JSONResponse(content={"error": f"Error al procesar el payload: {str(e)}"}, status_code=400)

    # Validación básica para evitar procesar mensajes mal formados
    if not from_number or not body:
        logger.warning("Mensaje recibido sin número de teléfono o cuerpo del mensaje")
        return JSONResponse(content={"status": False, "error": "Datos incompletos"}, status_code=400)

    # Crear o actualizar la sesión del usuario
    if from_number not in user_sessions:
        logger.debug(f"Creando nueva sesión para el usuario: {from_number}")
        user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
    session = user_sessions[from_number]
    session.update_activity()
    conversation_history = session.history

    # Recuperar mensajes históricos desde la base de datos y agregarlos al historial
    try:
        logger.debug(f"Recuperando mensajes históricos para el número: {from_number}")
        
        # Obtener mensajes ordenados por tiempo (los más antiguos primero)
        messages_db = db.Search(Message(number=from_number, source="whatsapp"), order='asc', limit=50) or []
        
        # Limpiar el historial antes de agregar mensajes para evitar duplicados
        conversation_history.messages.clear()
        
        # Añadir los mensajes al historial en el orden correcto
        for msg in messages_db:
            if msg.direction == "inbound":
                conversation_history.add_user_message(msg.message)
                logger.debug(f"Mensaje histórico (usuario): {msg.message[:30]}...")
            elif msg.direction == "outbound":
                conversation_history.add_ai_message(msg.message)
                logger.debug(f"Mensaje histórico (asistente): {msg.message[:30]}...")
            
    except Exception as e:
        logger.error(f"Error al recuperar mensajes históricos: {str(e)}")

    # Agregar mensaje actual del usuario al historial y guardarlo en la base de datos
    conversation_history.add_user_message(body)
    user_message = Message(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        senderName=sender_name,
        message=body,
        number=from_number,
        uid=uid,
        direction="inbound",
        mtype="text",
        source="whatsapp",
        latitude=latitude,
        longitude=longitude
    )
    logger.debug(f"Guardando mensaje del usuario en BD: {body[:30]}...")
    db.Insert(user_message)
    await manage_message_history(db, from_number)
    
    mexico_tz = pytz.timezone('America/Mexico_City')
    current_datetime = datetime.now(mexico_tz)
    date_string = current_datetime.strftime("%Y-%m-%d")
    hour = current_datetime.strftime("%I:%M:%S %p")
    
    try:
        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(customer_name=sender_name,call_sid=uid,date2=date_string,
            yoga_number=user_message.number,
            now=hour,
            folio="Pendiente de generar",
            address=address if 'address' in locals() else "No he recibido ubicación",
            image_description=image_description if 'image_description' in locals() else "No se ha recibido ninguna imagen"
        )
        # Añadir instrucción para evitar generación automática de reportes
        if from_number in report_sessions and report_sessions[from_number]["images"]:
            system_prompt += "\n\nINSTRUCCIÓN IMPORTANTE: NO crees ningún reporte ni menciones folios en tu respuesta. El usuario debe decir EXPLÍCITAMENTE 'Crear reporte' para que se genere. No inventes folios ni digas que has creado un reporte a menos que yo te confirme que el reporte ya fue generado."

        llm_service = OpenAIService(
            config=config,
            api_key=os.getenv("OPENAI_API_KEY"),
            system=system_prompt,
            function_manager=function_manager
        )

        # Procesar la imagen si está disponible
        if 'image_description' in locals() and image_description:
            image_message = f"[Imagen recibida. Descripción: {image_description}]"
            # No es necesario añadirlo otra vez ya que el cuerpo del mensaje ya contiene esta info
            # conversation_history.add_user_message(image_message)

        # Formatear el historial de mensajes para el modelo
        formatted_history = [
            {"role": "user", "content": message.content} if isinstance(message, HumanMessage)
            else {"role": "system", "content": message.content} if isinstance(message, SystemMessage)
            else {"role": "assistant", "content": message.content}
            for message in conversation_history.messages
        ]
        
        # Convertir formatted_history en un solo string para user_input
        user_input = "\n".join(f"{msg['role']}: {msg['content']}" for msg in formatted_history)
        logger.debug(f"Input preparado para el modelo (primeros 100 caracteres): {user_input[:100]}...")

        # Generar la respuesta del modelo usando el historial completo
        model_response = llm_service.generate_response(user_input=user_input)
        response_content = ""
        async for response in model_response:
            response_content += str(response)
            
        # Asegurar que response_content sea un string
        if isinstance(response_content, list):
            response_content = " ".join([str(item) for item in response_content])
        elif not isinstance(response_content, str):
            response_content = str(response_content)
        
        report_creation_patterns = ["he creado tu reporte", "he generado tu reporte", "tu reporte ha sido", 
                            "el número de folio", "el folio de tu reporte", "se ha generado tu reporte"]
        
        if from_number in report_sessions and report_sessions[from_number]["images"]:
            if any(pattern in response_content.lower() for pattern in report_creation_patterns):
                logger.warning(f"Detectado intento de creación automática de reporte: '{response_content[:50]}...'")
        # Sustituir con mensaje seguro
            response_content = "He guardado toda la información y las imágenes que has enviado. Si deseas finalizar y generar tu reporte ahora, por favor dímelo explícitamente usando las palabras 'Crear reporte'."
        # Guardar la respuesta en el historial y en la base de datos
        conversation_history.add_ai_message(response_content)
        assistant_message = Message(
            time=current_datetime,
            senderName="Assistant",
            message=response_content,
            number=from_number,
            uid=uid,
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )
        logger.debug(f"Guardando respuesta del asistente en BD: {response_content[:30]}...")
        db.Insert(assistant_message)
        await manage_message_history(db, from_number)

    except Exception as e:
        logger.error(f"Error al generar la respuesta: {str(e)}")
        return JSONResponse(content={"error": f"Error al generar respuesta: {str(e)}"}, status_code=500)
    
    # Enviar la respuesta a través de Chat2Desk
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        # Check if the response contains phrases that could trigger finalization
        blocked_phrases = [
                "ya terminé", "ya termine", "listo", "finalizar reporte", 
                "estoy listo", "he terminado", "terminar", "finalizar",
                "terminé de enviar", "no más imágenes", "cuando hayas terminado",
                "avísame cuando", "solo indícamelo", "indicarme cuando desees"
                        ]

        for phrase in blocked_phrases:
            if phrase.lower() in response_content.lower():
                # Modify the message to avoid triggering phrases
                response_content = response_content.replace(
                    phrase, 
                    f"{phrase[0]}*{phrase[1:]}"  # Add an asterisk to prevent exact matching
                )
                logger.warning(f"Modified trigger phrase in bot response: {phrase}")

        function_call_patterns = [
            "transfer_to_group", 
            "call_sid =",
            "functions.hangup",
            "await save_client_selection",
            "save_client_selection"
        ]
        # Check if the response looks like a function call or system instruction
        is_function_call = any(pattern in response_content for pattern in function_call_patterns)

        # If this looks like a function call instruction or system message, replace it
        if is_function_call:
            logger.warning(f"Detected function call in response: {response_content}")
            
            # Check if it's a transfer request
            if "transfer_to_group" in response_content:
                # Add to transferred_numbers dictionary with expiration timestamp
                expiration_time = datetime.now().timestamp() + transfer_timeout
                transferred_numbers[from_number] = expiration_time
                logger.info(f"Transfer for {from_number} active until {datetime.fromtimestamp(expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")
                
                response_content = "Estoy transfiriendo tu conversación a un agente humano que podrá asistirte mejor. Un agente te atenderá en breve."
                
                # Execute the actual transfer - CHANGE FROM ASYNC TO SYNC
                phone_number = from_number
                try:
                    # Extract group_id if specified
                    group_id = None
                    import re
                    group_match = re.search(r'transfer_to_group\(.*?(\d+).*?\)', response_content)
                    if group_match:
                        group_id = int(group_match.group(1))
                    
                    # Execute the transfer function SYNCHRONOUSLY
                    result = await transfer_to_group(phone_number, group_id)
                    logger.info(f"Transfer result: {result}")
                except Exception as e:
                    logger.error(f"Error executing transfer: {str(e)}")
                    # If transfer fails, remove from transferred numbers
                    if from_number in transferred_numbers:
                        del transferred_numbers[from_number]
            
            # Check if it's a hangup or farewell
            elif any(p in response_content for p in ["functions.hangup", "call_sid ="]):
                response_content = "¡Entendido! Que tengas un excelente día. ¡Hasta pronto!"

            # Generic fallback for other function calls
            else:
                response_content = "Estoy procesando tu solicitud. Dame un momento por favor."

        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": response_content
        }
        
        response = requests.post(chat2desk_url, json=data, headers=headers)
        
        if response.status_code == 200:
            logger.debug(f"Respuesta enviada exitosamente a Chat2Desk")
            content = {"status": True, "message": "Respuesta enviada por Chat2Desk"}
        else:
            logger.error(f"Error al enviar mensaje a Chat2Desk: {response.status_code} - {response.text}")
            content = {"status": False, "error": f"Error al enviar mensaje: {response.status_code}"}

    except requests.RequestException as e:
        logger.error(f"Error de conexión con Chat2Desk: {str(e)}")
        content = {"status": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        logger.error(f"Error inesperado al enviar mensaje: {str(e)}")
        content = {"status": False, "error": f"Error inesperado: {str(e)}"}

    # Después de enviar la respuesta a través de Chat2Desk y justo antes de return JSONResponse
    # Verificar si el mensaje del usuario indica despedida y la respuesta del bot también
    farewell_keywords = ["gracias", "adiós", "adios", "hasta luego", "chao", "bye", "es todo", "terminar"]
    bot_farewell_indicators = ["que tengas", "hasta luego", "adiós", "adios", "buen día", "hasta pronto"]

    # # Helper function to remove number from transferred set after timeout
    # async def remove_from_transferred(number, delay_seconds):
    #     await asyncio.sleep(delay_seconds)
    #     if number in transferred_numbers:
    #         transferred_numbers.remove(number)
    #         logger.debug(f"Removed {number} from transferred numbers list after {delay_seconds} seconds")
    # Función de limpieza definida fuera del bloque if para evitar problemas de acceso
    async def delayed_cleanup_msgs(phone_number):
        try:
            await asyncio.sleep(5)  # Esperar 5 segundos para asegurar que el mensaje se entregó
            db = LocalStorage()
            
            # Usar el método para eliminar mensajes por número
            # Implementa este método en la clase LocalStorage
            conn = psycopg2.connect(dbname=db.dbName, user=db.user, password=db.password, host=db.host, port=db.port)
            cursor = conn.cursor()
            
            # SQL directo para eliminar mensajes por número
            cursor.execute("DELETE FROM messages WHERE number = %s", [phone_number])
            count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Se eliminaron {count} mensajes para el número {phone_number} por despedida.")
            
            # Eliminar la sesión también
            if phone_number in user_sessions:
                del user_sessions[phone_number]
                logger.debug(f"Sesión de {phone_number} finalizada por despedida.")
                
        except Exception as e:
            logger.error(f"Error al eliminar mensajes: {str(e)}")

    if (any(keyword in body.lower() for keyword in farewell_keywords) and 
        any(indicator in response_content.lower() for indicator in bot_farewell_indicators)):
        
        # Crear tarea sin esperar a que termine
        asyncio.create_task(delayed_cleanup_msgs(from_number))

    return JSONResponse(content=content)

def format_phone_number(phone):
    """
    Formatea un número de teléfono para usarlo con Chat2Desk.
    
    Args:
        phone (str): Número de teléfono en cualquier formato
        
    Returns:
        str: Número formateado (sin '+' y con prefijo 521 si es de México)
    """
    # Eliminar cualquier caracter no numérico
    phone = ''.join(filter(str.isdigit, phone))
    
    # Asegurarse que tenga el prefijo de México para WhatsApp (521)
    if phone.startswith('52') and len(phone) >= 12:
        # Ya tiene el formato correcto (52 + 1 + 10 dígitos)
        return phone
    elif phone.startswith('52') and len(phone) == 10:
        # Falta el '1' después del código de país
        return f"521{phone[2:]}"
    elif len(phone) == 10:
        # Solo tiene los 10 dígitos, agregar prefijo 521
        return f"521{phone}"
    elif len(phone) == 12 and phone.startswith('52'):
        # Ya tiene formato internacional (52 + 10 dígitos)
        return phone
    
    # Si no coincide con ningún patrón conocido, devolver como está
    return phone

@router.post("/report-status")
async def report_status_update(request: Request):
    """
    Endpoint para recibir actualizaciones de estados de reportes y enviar notificaciones
    por WhatsApp a los clientes correspondientes. Solo se envían notificaciones
    para estados "en progreso" y "concluido".
    """
    try:
        # Obtener los datos del cuerpo de la solicitud
        payload = await request.json()
        logger.debug(f"Payload de actualización de reporte recibido: {payload}")
        
        # Validar campos requeridos
        required_fields = ["reportId", "reportStatus", "phoneNumber"]
        for field in required_fields:
            if field not in payload:
                return JSONResponse(
                    content={"error": f"Campo requerido ausente: {field}"}, 
                    status_code=400
                )
        
        # Extraer datos
        report_id = payload["reportId"]
        report_status = payload["reportStatus"].lower()  # Convertir a minúsculas para comparación
        phone_number = payload["phoneNumber"]
        
        # Solo procesar estados específicos
        if report_status != "en progreso" and report_status != "concluido":
            logger.debug(f"Estado '{report_status}' no requiere notificación. Solo se notifican 'en progreso' y 'concluido'")
            return JSONResponse(content={
                "status": True,
                "message": f"No se requiere notificación para el estado: {report_status}"
            })
        
        # Formatear el número de teléfono para Chat2Desk
        original_phone = phone_number
        phone_number = format_phone_number(phone_number)
        logger.debug(f"Número de teléfono formateado: {original_phone} -> {phone_number}")
            
        # Buscar cliente en Chat2Desk
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_base_url = "https://api.chat2desk.com.mx/v1"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        # Buscar cliente por número de teléfono
        search_url = f"{chat2desk_base_url}/clients"
        params = {"phone": phone_number}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error al buscar cliente en Chat2Desk: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error al buscar cliente: {response.status_code}"}, 
                status_code=500
            )
            
        response_data = response.json()
        logger.debug(f"Respuesta de búsqueda de cliente: {response_data}")
        
        # Verificar si se encontró el cliente basado en la estructura de respuesta de Chat2Desk
        if response_data.get("status") != "success" or not response_data.get("data") or len(response_data.get("data", [])) == 0:
            # Cliente no encontrado, lo creamos
            logger.debug(f"Cliente no encontrado, creando nuevo cliente con número: {phone_number}")
            create_url = f"{chat2desk_base_url}/clients"
            client_data = {
                "phone": phone_number,
                "transport": "wa_direct"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(create_url, json=client_data, headers=headers)
                
            if response.status_code != 200:
                logger.error(f"Error al crear cliente en Chat2Desk: {response.status_code} - {response.text}")
                return JSONResponse(
                    content={"error": f"Error al crear cliente: {response.status_code}"}, 
                    status_code=500
                )
                
            create_response = response.json()
            

            if create_response.get("status") != "success":
                logger.error(f"Error en la respuesta al crear cliente: {create_response}")
                return JSONResponse(
                    content={"error": "Error al crear cliente en Chat2Desk"}, 
                    status_code=500
                )
                
            client_id = create_response.get("data", {}).get("id")
        else:
            # Cliente encontrado
            client_id = response_data.get("data")[0].get("id")
            
        # Obtener información del canal (channel_id)
        if not client_id:
            return JSONResponse(
                content={"error": "No se pudo obtener el ID del cliente"}, 
                status_code=500
            )
            
        # En lugar de consultar los canales, usar un valor fijo
        channel_id = 43347  # Valor fijo conocido para el canal de WhatsApp
        logger.debug(f"Cliente identificado: client_id={client_id}, usando channel_id fijo={channel_id}")
        
        # Preparar y enviar el mensaje al cliente
        message_url = f"{chat2desk_base_url}/messages"
        
        # Construir mensaje según el estado específico del reporte
        if report_status == "en progreso":
            message_text = f"Su reporte #{report_id} ya se encuentra en proceso de atención. Un técnico está trabajando para resolver su solicitud lo antes posible."
        elif report_status == "concluido":
            message_text = f"¡Buenas noticias! Su reporte #{report_id} ha sido concluido satisfactoriamente. Gracias por su paciencia."
        
        # Si hay información adicional en el payload, incluirla en el mensaje
        if "additionalInfo" in payload and payload["additionalInfo"]:
            message_text += f"\n\nInformación adicional: {payload['additionalInfo']}"
            
        message_data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": message_text
        }
        
        # Enviar el mensaje
        async with httpx.AsyncClient() as client:
            response = await client.post(message_url, json=message_data, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error al enviar mensaje: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error al enviar mensaje: {response.status_code}"}, 
                status_code=500
            )
            
        send_response = response.json()
        if send_response.get("status") != "success":
            logger.error(f"Error en la respuesta al enviar mensaje: {send_response}")
            return JSONResponse(
                content={"error": "Error al enviar mensaje en Chat2Desk"}, 
                status_code=500
            )
            
        # Almacenar el mensaje en la base de datos local
        db = LocalStorage()
        message = Message(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            senderName="Sistema",
            message=message_text,
            number=phone_number,
            uid=f"report-{report_id}-{datetime.now().timestamp()}",
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )
        db.Insert(message)
        await manage_message_history(db, phone_number)
        
        logger.debug(f"Mensaje de actualización enviado exitosamente para el reporte #{report_id} - Estado: {report_status}")
        
        return JSONResponse(content={
            "status": True, 
            "message": "Notificación de actualización de reporte enviada",
            "reportId": report_id,
            "clientId": client_id,
            "reportStatus": report_status
        })
        
    except Exception as e:
        logger.error(f"Error al procesar la actualización del reporte: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": f"Error al procesar la solicitud: {str(e)}"}, 
            status_code=500
        )
@router.get("/health")
async def health():
    import psutil, ping3
    ls = LocalStorage()
    configs = ls.GetAll(Config)
    configs = { c.name: c.value for c in configs }

    domains = json.loads(configs.get("PingDomains")) if 'PingDomains' in configs else []
    domains.extend([
        { "name": "AWS", "domain": 'ec2.amazonaws.com'},
        { "name": "Google", "domain": 'google.com'},
        { "name": "Twilio", "domain": "chunderw-gll.twilio.com"}
    ])

    try:
        temperatures = psutil.sensors_temperatures()
        if temperatures:
            temperature = temperatures['coretemp'][0].current
        else:
            temperature = False
    except (AttributeError, KeyError):
        temperature = False
    
    pings = []
    for domain in domains:
        ping = ping3.ping(domain["domain"])
        ping = int(ping * 1000) if ping is not None else False
        pings.append({ "domain": domain["domain"], "ping": ping, "name": domain["name"] })

    metrics = {
        'processor': psutil.cpu_percent(interval=1),
        'memory': psutil.virtual_memory().percent,
        'storage': psutil.disk_usage('/').percent,
        'temperature': temperature,
        'ping': pings
    }
    
    return metrics


# ---------------------
# Definición de la aplicación FastAPI
# ---------------------
app = FastAPI(lifespan=lifespan)
app.include_router(router)