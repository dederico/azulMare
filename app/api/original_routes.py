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
from collections import OrderedDict
from datetime import datetime, timedelta
from app.services.llm.deepseek_service import DeepSeekService

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
from app.services.functions.implementations.nearest_office import find_nearest_government_office
from app.util.rate_limiter import image_processing_queue


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
from app.services.functions.implementations.save_selection2 import save_client_selection2
from app.services.functions.implementations.save_selection import find_row_and_update_selection
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
from threading import RLock
from app.services.functions.implementations.save_selection2 import save_user_answer, get_user_answer

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

# Diccionario para almacenar reportes en progreso
report_sessions = {}  # key: phone_number, value: {images: [], image_descriptions: [], location: str, timestamp: datetime}
reports_lock = threading.Lock()
report_sessions_lock = RLock()  # More robust than a simple Lock
reports_in_progress = {}
transferred_numbers = {}  # key: phone_number, value: expiration_timestamp
transfer_timeout = 15 * 60  # 15 minutes in seconds
last_response_time = {}  # Para rastrear cuándo se envió la última respuesta a cada número
completed_reports = {}  # key: phone_number, value: {timestamp: datetime, folio: str}
finalized_report_numbers = set()
# Ahora, añade esta nueva función para verificar si un número ya tiene un reporte reciente

import re

def detect_and_store_user_data(from_number: str, body: str):
    """
    Detecta y guarda múltiples campos en un solo mensaje.
    Incluye nombre, tipo, calle, número, colonia.
    No procesa selection1. Las imágenes van en selection8.
    """
    patterns = {
        "selection2": r"(?i)nombre\s*:\s*([^\n,]+)",
        "selection4": r"(?i)tipo\s*:\s*([^\n,]+)",
        "selection5": r"(?i)calle\s*:\s*([^\n,]+)",
        "selection6": r"(?i)n[uú]mero\s*:\s*([^\n,]+)",
        "selection7": r"(?i)colonia\s*:\s*([^\n,]+)"
    }

    saved_fields = []

    for selection_key, pattern in patterns.items():
        matches = re.findall(pattern, body)
        for match in matches:
            value = match.strip()
            save_user_answer(from_number, selection_key, value)
            saved_fields.append((selection_key, value))
    
    if saved_fields:
        log_summary = "; ".join([f"{key}='{val}'" for key, val in saved_fields])
        logger.info(f"[{from_number}] Campos detectados y guardados: {log_summary}")
    else:
        logger.debug(f"[{from_number}] No se detectó ningún campo en: {body.strip()}")

def has_recent_report(phone_number, max_age_minutes=10):
    """
    Verifica si un número tiene un reporte creado recientemente.
    
    Args:
        phone_number (str): Número de teléfono a verificar
        max_age_minutes (int): Tiempo máximo en minutos para considerar un reporte como "reciente"
        
    Returns:
        dict: None si no hay reporte reciente, o información del reporte si existe
    """
    if phone_number not in completed_reports:
        return None
    
    # Verificar si el reporte es reciente
    report_info = completed_reports[phone_number]
    current_time = datetime.now().timestamp()
    elapsed_minutes = (current_time - report_info['timestamp']) / 60
    
    if elapsed_minutes <= max_age_minutes:
        return report_info
    
    # Si el reporte es antiguo, eliminarlo del registro y retornar None
    del completed_reports[phone_number]
    return None


# Añade esta función wrapper alrededor de save_client_selection
async def save_client_selection_with_deduplication(yoga_number, selection1, selection2, selection3,
                                       selection4, selection5, selection6, selection7, 
                                       selection8=None, images_list=None, descriptions_list=None):
    """
        Wrapper around save_client_selection2 for report deduplication.
    
    Args:
        yoga_number (str): Phone number
        selection1 (str): Asunto ID (e.g., "984" for baches)
        selection2 (str): Name of the reporter
        selection3 (str): Always empty string ""
        selection4 (str): Report description
        selection5 (str): Street name
        selection6 (str): Street number (default "100")
        selection7 (str): Neighborhood name
        selection8 (str, optional): Legacy parameter (not used)
        images_list (list, optional): List of image URLs
        descriptions_list (list, optional): List of image descriptions
        
    Returns:
        str: Report folio number
    """
    # Verificar si ya existe un reporte reciente para este número
    recent_report = has_recent_report(yoga_number)
    if recent_report:
        logger.warning(f"Evitando reporte duplicado para {yoga_number}. Folio existente: {recent_report['folio']}")
        return recent_report['folio']  # Retornar el folio del reporte existente
    
    # Si no hay reporte reciente, proceder con la creación
    try:
        if not selection1 or not selection1.isdigit():
            selection1 = "984"

        if not selection2:
            selection2 = "Ciudadano"

        selection3 = ""
        logger.debug(f"Creating report with params: asunto={selection1}, name={selection2}, " +
                   f"desc={selection4}, calle={selection5}, numero={selection6}, colonia={selection7}")
        logger.debug(f"Images: {len(images_list) if images_list else 0}")

        folio = await save_client_selection2(
            yoga_number=yoga_number, 
            selection1=selection1, 
            selection2=selection2, 
            selection3=selection3,
            selection4=selection4, 
            selection5=selection5, 
            selection6=selection6, 
            selection7=selection7,
            selection8=selection8, 
            images_list=images_list,  # Asegúrate de que este parámetro se pase
            descriptions_list=descriptions_list
        )
        
        # Registrar este reporte exitoso
        completed_reports[yoga_number] = {
            'timestamp': datetime.now().timestamp(),
            'folio': folio
        }
        
        # Programar eliminación del registro después de cierto tiempo (e.g., 30 minutos)
        asyncio.create_task(remove_from_completed_reports(yoga_number, 1800))
        
        return folio
    except Exception as e:
        logger.error(f"Error al crear reporte para {yoga_number}: {str(e)}")
        raise


# Using OrderedDict as a simple TTL cache
class TTLCache:
    def __init__(self, max_size=1000, ttl_seconds=3600):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def add(self, key):
        # Clean expired entries first
        self._clean_expired()
        
        # Add new entry with timestamp
        self.cache[key] = datetime.now()
        
        # If over size limit, remove oldest
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def contains(self, key):
        if key not in self.cache:
            return False
        
        # Check if expired
        timestamp = self.cache[key]
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self.cache[key]
            return False
        
        return True
    
    def _clean_expired(self):
        # Remove expired entries
        now = datetime.now()
        expired_keys = [k for k, v in self.cache.items() 
                       if now - v > timedelta(seconds=self.ttl_seconds)]
        for key in expired_keys:
            del self.cache[key]
    
    # Add this method to support len()
    def __len__(self):
        self._clean_expired()  # Clean expired entries first
        return len(self.cache)

async def analyze_image_with_rate_limit(client, photo_url):
    """
    Analyze an image with rate limiting to prevent API overload.
    
    Args:
        client: OpenAI client instance
        photo_url: URL of the image to analyze
        
    Returns:
        str: Image description from the analysis
    """
    try:
        logger.debug(f"Starting rate-limited image analysis for: {photo_url}")
        
        # Download the image with timeout
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url, timeout=10) as response:
                response.raise_for_status()
                image_content = BytesIO(await response.read())
        
        # Rate-limited OpenAI API call
        async def _analyze_with_openai():
            image_analysis = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe esta imagen en una frase breve (máximo 15 palabras)."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_content.getvalue()).decode('utf-8')}",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=100,
            )
            return image_analysis.choices[0].message.content
            
        # Use the queue to process with rate limiting
        description = await image_processing_queue.add_task(_analyze_with_openai)
        return description
        
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return f"Error al analizar la imagen: {str(e)}"
    
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
        db = LocalStorage()

        numbers_to_process = []

        with report_sessions_lock:
            for number, session in list(report_sessions.items()):
                elapsed = (now - session["timestamp"]).total_seconds()
                if elapsed > 180:  # 3 minutos de inactividad
                    # Solo finalizar si hay imágenes
                    # Only consider sessions with images
                    if session["images"]:
                        numbers_to_process.append(number)
                    
        # Process them outside the lock
        for number in numbers_to_process:
            try:
                with report_sessions_lock:
                    if number not in report_sessions:
                        continue
                        
                    session = report_sessions[number]
                    if not session["images"]:
                        continue
                
                # Process the report without holding the lock on the entire report_sessions dict
                location = session["location"] or "ubicación no especificada"
                
                # Use the new process_and_save_report function
                result = await process_and_save_report(
                    number, 
                    location,
                    session["images"],
                    session["image_descriptions"]
                )
                
                # Only clean up if successful
                if result['status'] == 'success':
                    logger.info(f"Auto-finalization successful: {result['message']}")
                    mark_report_as_completed(number)
                    with report_sessions_lock:
                        if number in report_sessions:
                            del report_sessions[number]
                else:
                    logger.warning(f"Auto-finalization failed for {number}: {result.get('message', 'Unknown error')}")
                        
            except Exception as e:
                logger.error(f"Error al finalizar reporte automáticamente: {str(e)}")
                # Still try to clean up
                with report_sessions_lock:
                    if number in report_sessions:
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
    # llm_service = OpenAIService(
    #     config=config,
    #     api_key=OPENAI_API_KEY,
    #     system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date2=date_string, now=hour, folio="folio"),
    #     function_manager=function_manager
    # )

    llm_service = DeepSeekService(
        config=config,
        api_key=DEEPSEEK_API_KEY,
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

# Add this at the module level
recently_completed_reports = {}  # key: phone_number, value: {timestamp, message_count}

# This function should be called when a report is successfully created
def mark_report_as_completed(phone_number):
    """
    Mark a phone number as having recently completed a report.
    This helps prevent normal thank you/farewell messages from triggering
    another report finalization cycle.
    
    Args:
        phone_number (str): User's phone number
    """
    logger.info(f"MARCANDO NÚMERO {phone_number} COMO COMPLETADO RECIENTEMENTE")  # Log explícito

    recently_completed_reports[phone_number] = {
        'timestamp': datetime.now().timestamp(),
        'message_count': 0  # Count of messages sent after completion
    }
    
    # Schedule cleanup after 3 minutes
    asyncio.create_task(remove_from_recently_completed(phone_number, 180))

# Helper function to remove from the tracking dict after a timeout
async def remove_from_recently_completed(phone_number, delay_seconds):
    """Remove a number from recently_completed_reports after a delay."""
    try:
        await asyncio.sleep(delay_seconds)
        if phone_number in recently_completed_reports:
            del recently_completed_reports[phone_number]
            logger.debug(f"Removed {phone_number} from recently completed reports tracking")
    except Exception as e:
        logger.error(f"Error removing {phone_number} from recently completed reports: {str(e)}")

# Modified is_finalization_message function
def is_finalization_message(text, from_number=None):
    """
    Determine if a message is attempting to finalize a report.
    This enhanced version detects many more ways to express "finalize a report" in Spanish.
    It also considers conversation context to avoid treating post-report thank you messages
    as new finalization requests.
    
    Args:
        text (str): The message text to analyze
        from_number (str, optional): The phone number of the sender for context checking
        
    Returns:
        bool: True if the message should be treated as report finalization
    """
    if not text or not isinstance(text, str):
        return False
    
    # Convert to lowercase for case-insensitive matching
    text_lower = text.lower()
    
    # Check if this number just completed a report
    if from_number and from_number in recently_completed_reports:
        completion_info = recently_completed_reports[from_number]
        current_time = datetime.now().timestamp()
        elapsed_seconds = current_time - completion_info['timestamp']
        
        # If report was completed in the last 60 seconds and this is one of the first 2 messages after
        if elapsed_seconds < 60 and completion_info['message_count'] < 2:
            # Increment the message counter
            completion_info['message_count'] += 1
            
            # Common thank you and farewell phrases in Spanish
            post_report_phrases = [
                "gracias", "mil gracias", "muchas gracias", "excelente", "perfecto",
                "genial", "que bueno", "qué bueno", "estupendo", "magnífico",
                "es todo", "eso es todo", "eso era todo", "es todo por ahora",
                "es todo lo que necesitaba", "era todo", "no necesito nada más",
                "así está bien", "así esta bien", "está bien", "esta bien", 
                "ok", "okay", "bien", "bueno", "de acuerdo", "entendido"
            ]
            
            # If the message looks like a thank you after report completion
            if any(phrase in text_lower for phrase in post_report_phrases):
                logger.debug(f"Detected post-report thank you message, not treating as finalization: '{text}'")
                return False
    
    # 1. Direct finalization keywords
    direct_keywords = [
        # Basic completion terms
        "listo", "lista", "ya terminé", "ya termine", "terminé", "termine", "he terminado", 
        "estoy listo", "estoy lista", "finalizar", "finaliza", "finalizado", "culminar",
        "completar", "completado", "completo", "completa", "acabar", "acabado", "acabé", 
        "acabe", "concluir", "concluido", "concluso", "concluyó", "concluyo",
        
        # Report specific
        "generar reporte", "genera reporte", "crear reporte", "crea reporte", "hacer reporte", 
        "haz reporte", "levantar reporte", "levanta reporte", "enviar reporte", "envía reporte",
        "reportar", "reporta", "reportarlo", "ingresar reporte", "ingresa reporte", "manda reporte",
        "mandar reporte", "envia", "enviar", "registrar", "registra", "registrarlo", "registro",
        
        # Send/submit variations
        "enviar", "envía", "mandar", "manda", "envíalo", "envialo", "mándalo", "mandalo",
        "someter", "somete", "somételo", "sometelo", "presentar", "presenta", "preséntalo",
        "presentarlo", "subir", "sube", "súbelo", "súbelo", "procesar", "procesa", "procésalo",
        
        # OK/Proceed variations
        "adelante", "procede", "proceda", "continua", "continúa", "avanza", "ejecuta", "ejecutar",
        "seguir adelante", "sigue adelante", "dale", "dale paso", "confirmar", "confirma", "aceptar",
        "acepta", "aprobar", "aprueba", "ok", "okay", "sí", "si", "afirmativo",
        
        # Añadir estas expresiones específicas
        "son todas", "es todo", "todas", "solo estas", "eso es todo", "ya están todas"
    ]
    
    # 2. Phrase patterns that indicate finalization
    finalization_phrases = [
        "ya está", "ya esta", "eso es todo", "es todo", "eso sería todo", "con eso", 
        "así está bien", "asi esta bien", "ya quedó", "ya quedo", "está completo", "esta completo",
        "puedes finalizar", "puedes terminar", "puedes proceder", "puedes continuar",
        "puedes procesar", "puedes enviarlo", "puedes mandarlo", "puedes registrarlo",
        "por favor finaliza", "por favor termina", "por favor procede", "por favor continúa",
        "favor de finalizar", "favor de terminar", "favor de proceder", "favor de continuar",
        "favor de enviarlo", "favor de mandarlo", "favor de registrarlo",
        "no más fotos", "no más imágenes", "no más", "solo esas fotos", "solo esas imágenes",
        "son todas las fotos", "son todas las imágenes", "ya tengo todas", "ya mandé todas",
        "ya envié todas", "puedes hacer", "puedes generar", "genera el reporte", "crea el reporte",
        "son todas", "es todo", "todas", "esas son todas"  # Repetimos aquí para asegurar detección
    ]
    
    # 3. Negative-word filters (words that might indicate the user is NOT ready)
    negative_indicators = [
        "no estoy listo", "no he terminado", "no está listo", "no esta listo", "todavía no", 
        "aún no", "falta", "faltan", "espera", "espere", "aguanta", "aguante", "detente", 
        "más tarde", "luego", "después", "despues", "no lo envíes", "no lo envies", 
        "no lo mandes", "no finalices", "no termines", "no generes", "no crees",
        "no quiero finalizar", "no quiero terminar", "no deseo finalizar", "no deseo terminar",
        "no lo hagas"
    ]

    # Verificación exacta para frases comunes muy cortas
    exact_phrases = ["son todas", "es todo", "listo", "todas", "solo estas"]
    if text_lower.strip() in exact_phrases:
        return True
    
    # Check for direct keywords (simple full or partial matches)
    if any(keyword in text_lower.split() or keyword in text_lower for keyword in direct_keywords):
        # But make sure none of the negative indicators are present
        if not any(neg in text_lower for neg in negative_indicators):
            return True
    
    # Check for phrase patterns (more complex expressions)
    if any(phrase in text_lower for phrase in finalization_phrases):
        # But make sure none of the negative indicators are present
        if not any(neg in text_lower for neg in negative_indicators):
            return True
    
    # Additional context-aware checks for very short responses
    if len(text_lower.split()) <= 3:  # Very short responses
        # Common short approvals
        short_approvals = ["ok", "sí", "si", "yes", "ya", "dale", "eso", "ese", "esta bien", "está bien", "listo"]
        if any(text_lower == word or text_lower.startswith(word + " ") or text_lower.endswith(" " + word) for word in short_approvals):
            return True
            
        # Check for standalone "1" or "ok" which users sometimes send as confirmation
        if text_lower in ["1", "ok", "👍", "👌"]:
            return True
    
    # If none of the above conditions match, it's not a finalization message
    return False

async def remove_from_completed_reports(number, delay_seconds):
    """Remove a number from completed_reports after a delay with error handling."""
    try:
        await asyncio.sleep(delay_seconds)
        if number in completed_reports:
            del completed_reports[number]
            logger.debug(f"Removed {number} from completed reports after {delay_seconds} seconds")
    except Exception as e:
        logger.error(f"Error removing {number} from completed reports: {str(e)}")

async def send_chat2desk_message(phone_number, client_id, channel_id, text):
    """Send a message via Chat2Desk API."""
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(chat2desk_url, json=data, headers=headers)
            
        if response.status_code == 200:
            logger.debug(f"Message sent successfully to Chat2Desk")
            return True
        else:
            logger.error(f"Error sending message to Chat2Desk: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Exception while sending Chat2Desk message: {str(e)}")
        return False


# Modify the process_and_save_report function
async def process_and_save_report(from_number, location, images=None, descriptions=None):
    """
    Process and save a report with improved error handling and deduplication.
    Returns a dict with status and additional information.
    
    Args:
        from_number (str): Sender's phone number
        location (str): Location information  
        images (list): List of image URLs
        descriptions (list): List of image descriptions
    """
    logger.debug(f"process_and_save_report: Processing report for {from_number}")
    
    # Initialize with empty lists if None
    images = images or []
    descriptions = descriptions or []
    
    # Log received images for debugging
    logger.debug(f"Received {len(images)} images for processing")
    for i, img in enumerate(images):
        logger.debug(f"  Image {i+1}: {img[:50]}...")
    
    # Check for recent report (deduplication)
    recent_report = has_recent_report(from_number)
    if recent_report:
        logger.warning(f"Recent report found for {from_number}, folio: {recent_report['folio']}")
        return {
            'status': 'duplicate',
            'message': f"Tu reporte ya fue creado recientemente (folio: {recent_report['folio']})",
            'folio': recent_report['folio']
        }
    
    # Check for empty images
    if not images:
        return {
            'status': 'no_images',
            'message': "No se han adjuntado imágenes al reporte. Por favor, envía al menos una imagen."
        }
    
    # Mark as in progress (with thread safety)
    with reports_lock:
        if from_number in reports_in_progress and reports_in_progress[from_number]:
            return {
                'status': 'in_progress',
                'message': "Tu reporte ya está siendo procesado. Por favor, espera unos momentos."
            }
        reports_in_progress[from_number] = True
    
    try:
        # Parse location into components
        street = "No especificada"
        neighborhood = "No especificada"
        street_number = "100"  # Default value
        
        if location:
            location_parts = location.split(',')
            if len(location_parts) >= 2:
                street = location_parts[0].strip()
                neighborhood = location_parts[1].strip()
            else:
                street = location

        selections = {
            "selection1": get_user_answer(from_number, 1),
            "selection2": get_user_answer(from_number, 2),
            "selection3": "",  # siempre vacío
            "selection4": get_user_answer(from_number, 4),
            "selection5": get_user_answer(from_number, 5),
            "selection6": get_user_answer(from_number, 6),
            "selection7": get_user_answer(from_number, 7),
        }

        # Create the report
        folio = await save_client_selection_with_deduplication(
            yoga_number=from_number,
            images_list=images,
            descriptions_list=descriptions,
            **selections
        )


        
        # Record successful report
        current_time = datetime.now().timestamp()
        completed_reports[from_number] = {
            'timestamp': current_time,
            'folio': folio,
        }
        
        # Schedule cleanup
        asyncio.create_task(remove_from_completed_reports(from_number, 1800))
        
        logger.info(f"Report successfully created for {from_number}, folio: {folio}")
        
        return {
            'status': 'success',
            'message': f"Reporte creado exitosamente. Folio: {folio}",
            'folio': folio
        }
        
    except Exception as e:
        logger.error(f"Error processing report for {from_number}: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error al procesar el reporte: {str(e)}"
        }
    finally:
        # Always release the "in progress" state
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
# Initialize the TTL cache - messages expire after 1 hour, max 1000 entries
processed_message_ids = TTLCache(max_size=1000, ttl_seconds=3600)

#Add this function to identify and filter out bot-originated messages
def is_bot_generated_message(message_text, recent_ai_messages=None):
    """
    Determines if a message was likely generated by our bot and echoed back.
    
    Args:
        message_text (str): The message text to analyze
        recent_ai_messages (list): Optional list of recent AI messages for comparison
        
    Returns:
        bool: True if the message appears to be from the bot, False otherwise
    """

    if not message_text:
        False

    # Check for specific bot message patterns
    exact_bot_patterns = [
        "he recibido tu imagen",
        "he recibido otra imagen",
        "tienes * en total", 
        "puedes enviar más imágenes",
        "puedes seguir enviando imágenes",
        "[image_received]",
        "ubicación registrada",
        "para finalizar tu reporte"
    ]

    # Use glob-style pattern matching (with * as wildcard)
    for pattern in exact_bot_patterns:
        if pattern.lower() in message_text.lower():
            return True
    
    # Check if the message closely matches a recent AI message
    if recent_ai_messages:
        for ai_message in recent_ai_messages:
            # If message is very similar to a recent AI message, it's likely an echo
            if ai_message == message_text or (
                len(ai_message) > 20 and len(message_text) > 20 and
                (ai_message in message_text or message_text in ai_message)
            ):
                return True
            
            # # Check similarity ratio for longer messages
            # if len(message_text) > 15 and len(ai_message) > 15:
            #     # Simple similarity check - shared words
            #     msg_words = set(message_text.lower().split())
            #     ai_words = set(ai_message.lower().split())
            #     common_words = msg_words.intersection(ai_words)
                
            #     # If they share more than 70% of words, likely an echo
            #     if len(common_words) / max(len(msg_words), len(ai_words)) > 0.7:
            #         return True
    
    return False

def get_images_from_payload(payload):
    global user_sessions, report_sessions
    """
    Extrae URLs de imágenes del payload de Chat2Desk.
    
    Args:
        payload (dict): El payload recibido de Chat2Desk
        
    Returns:
        list: Lista de URLs de imágenes válidas
    """
    fotos_urls = []
    from_number = payload.get('client', {}).get('phone')
    # Extraer foto si existe en el payload
    
    if payload.get("photo") and from_number:
        photo_url = payload.get("photo")
        # Verificar si debería ser una nueva sesión
        if from_number not in user_sessions and from_number in report_sessions:
            # Si hay user_sessions pero no report_sessions, limpiar report_sessions
            logger.info(f"Detectada posible sesión huérfana para {from_number}, limpiando datos de reporte antiguos")
            del report_sessions[from_number]
        
        if photo_url and isinstance(photo_url, str) and (photo_url.startswith('http') or 'storage.chat2desk.com' in photo_url):
            fotos_urls.append(photo_url)
            logger.debug(f"Foto capturada del payload: {photo_url}")
    
    # También podemos buscar fotos en otros campos si es necesario
    # Por ejemplo, si hubiera un campo "attachments" o similar
    
    return fotos_urls


@router.post("/whatsapp")
async def whatsapp(request: Request):
    logger.debug("Iniciando procesamiento del mensaje de WhatsApp.")
    # Configuración de base de datos y demás servicios
    db = LocalStorage()
    args = request.query_params
    config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
    function_manager = FunctionManager(registered_functions)
    #client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1")
    image_analysis_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Check if this is a message from a human agent with the human takeover message
    HUMAN_TAKEOVER_MESSAGE = "Buen día, gracias por comunicarse a Atención Ciudadana, le atiende"
    BOT_RETURN_MESSAGE = "Gracias por comunicarse a Atención Ciudadana. Procederé a reiniciar el chatbot"
    
    
    try:
        payload = await request.json()  # Recibimos el payload como JSON
        print(f"Payload recibido: {payload}")

        # IMPORTANTE: Verificar si es un mensaje de un cliente o una respuesta del sistema
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        message_type = payload.get('type', '')
        uid = payload.get('message_id', '')
        message_text = payload.get('text', '')
        channel_id = payload.get('channel_id')
        client_id = payload.get('client_id')
        hook_type = payload.get('hook_type', '')

        # Handle None values in body
        if body is None:
            body = ""
            logger.debug("Message with None body detected, setting to empty string")

        # PRIMERO - Verificar mensajes especiales de agentes
        if message_type == 'to_client' and message_text and message_text.startswith(HUMAN_TAKEOVER_MESSAGE):
            #Human agent is taking over - mark number as transferred with extended timeout
            logger.info(f"Human agent takeover detected for {from_number}")
            
            #Set a longer timeout (30 minutes) for explicit human takeover
            expiration_time = datetime.now().timestamp() + (30 * 60)
            transferred_numbers[from_number] = expiration_time
            
            # Store log message in database
            try:
                system_notification = Message(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    senderName="System",
                    message=f"[SYSTEM] Conversation transferred to human agent until {datetime.fromtimestamp(expiration_time).strftime('%H:%M:%S')}",
                    number=from_number,
                    uid=f"takeover-{datetime.now().timestamp()}",
                    direction="system",
                    mtype="text",
                    source="whatsapp"
                )
                db.Insert(system_notification)
            except Exception as e:
                logger.error(f"Error recording human takeover: {str(e)}")
            
            return JSONResponse(content={"status": True, "message": "Human agent takeover registered"})
            
        # Verificar si es un mensaje de despedida del agente humano
        if message_type == 'to_client' and message_text and BOT_RETURN_MESSAGE in message_text:
            # This is a goodbye message from human agent, return control to AI
            logger.info(f"!!! HUMAN AGENT GOODBYE DETECTED !!! Returning control to AI for {from_number}")
            
            if from_number in transferred_numbers:
                del transferred_numbers[from_number]
                
            # Send a confirmation message from the AI
            ai_greeting = "Consulta nuestro aviso de privacidad: https://bit.ly/4hd3eLy\n\n" + \
            "👋 ¡Bienvenido! Soy SAM, tu asistente virtual de Atención Ciudadana de SPGG. Recuerda para emergencias, reportes de seguridad o tránsito: marca al C4: 81 89 88 2000 🚓 🚑\n\n" + \
            "¿En qué puedo ayudarte hoy?"
            
            # Store the message in conversation history
            if from_number in user_sessions:
                conversation_history = user_sessions[from_number].history
                conversation_history.add_ai_message(ai_greeting)
            else:
                # Create new session if needed
                user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
                user_sessions[from_number].history.add_ai_message(ai_greeting)
                
            # AÑADIR ESTO - Enviar el mensaje a través de Chat2Desk
            try:
                api_token = os.getenv("CHAT2DESK_API_TOKEN")
                chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                
                headers = {
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                }
                
                data = {
                    "client_id": client_id,
                    "channel_id": channel_id,
                    "transport": "wa_direct",
                    "text": ai_greeting
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(chat2desk_url, json=data, headers=headers)
                
                # Store the message in the database
                assistant_message = Message(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    senderName="Assistant",
                    message=ai_greeting,
                    number=from_number,
                    uid=f"return-to-ai-{datetime.now().timestamp()}",
                    direction="outbound",
                    mtype="text",
                    source="whatsapp"
                )
                db.Insert(assistant_message)
                await manage_message_history(db, from_number)
                
                # IMPORTANTE - Retornar para evitar el procesamiento posterior
                return JSONResponse(content={"status": True, "message": "Control returned to AI"})
            
            except Exception as e:
                logger.error(f"Error sending AI greeting after return from human agent: {str(e)}")

        # Ahora procesar las imágenes cuando ya tenemos from_number
        fotos_urls = get_images_from_payload(payload)

        # Si hay un reporte en progreso, añadir las imágenes a su lista
        if from_number in report_sessions and fotos_urls:
            for foto_url in fotos_urls:
                if foto_url not in report_sessions[from_number]["images"]:
                    report_sessions[from_number]["images"].append(foto_url)
                    report_sessions[from_number]["image_descriptions"].append("Imagen adicional")
                    report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                    logger.info(f"Imagen añadida al reporte en progreso para {from_number}")

        # fotos_urls = []
        # # Si hay una foto en este mensaje, guardarla
        # if payload.get("photo"):
        #     photo_url = payload.get("photo")
        #     if photo_url and isinstance(photo_url, str) and (photo_url.startswith('http') or 'storage.chat2desk.com' in photo_url):
        #         fotos_urls.append(photo_url)
        #         logger.debug(f"Foto capturada del payload: {photo_url}")

        # Log ALL autoreply messages with full details
        if message_type == 'autoreply':
            # Create a proper debug log with all relevant fields
            
            # Obtener el texto y normalizarlo (eliminar espacios extras, convertir a minúsculas)
            raw_text = payload.get('text', '')
            if raw_text:
                # Imprimir el texto exacto para depuración
                print(f"Texto original: {repr(raw_text)}")
                # Normalizar el texto para hacer comparaciones más robustas
                # - Convertir a minúsculas
                # - Eliminar saltos de línea y caracteres especiales
                # - Eliminar espacios extras
                normalized_text = raw_text.lower().replace('\n', ' ').replace('-', '').strip()
                print(f"Texto normalizado: {repr(normalized_text)}")

                # Buscar patrones clave en lugar de coincidencias exactas
                if 'scenario' in normalized_text and 'title' in normalized_text and 'default' in normalized_text:
                    # Es probablemente un mensaje de escenario
                    if 'end' in normalized_text and 'finalizar' in normalized_text:
                        # Es un mensaje de finalización
                        logger.debug(f"Bloqueando mensaje de finalización de escenario: {uid}")
                        return JSONResponse(content={"status": True, "message": "Mensaje de escenario de finalización bloqueado"})
            
            debug_info = {
                "message_id": uid,
                "type": message_type,
                "hook_type": hook_type,
                "text_length": len(message_text) if message_text else 0,
                "text_sample": message_text[:50] if message_text else "None",
                "text_contains_scenario": 'scenario.scenarioTitle.default' in (message_text or ""),
                "text_contains_finalizar": 'End - Finalizar este chat' in (message_text or ""),
                "raw_text": repr(message_text),  # This shows exact string with escape codes
            }
            logger.debug(f"AUTOREPLY DEBUG: {json.dumps(debug_info)}")
            
            # Now with explicit detailed checks, try to catch these messages
            if message_text and 'scenario' in message_text and 'default' in message_text and 'End' in message_text:
                logger.info(f"BLOCKING SCENARIO MESSAGE: {repr(message_text)}")
                return JSONResponse(content={"status": True, "message": "Mensaje de escenario bloqueado con debug"})

        # Then continue with your existing filter logic:
        if (message_type == 'autoreply' and 
            'scenario.scenarioTitle.default' in (message_text or "") and 
            'End - Finalizar este chat' in (message_text or "")):
            
            logger.debug(f"Bloqueando mensaje autoreply de escenario de finalización: {uid}")
            return JSONResponse(content={"status": True, "message": "Mensaje de escenario de fin ignorado"})
        
        # Solo procesar mensajes que vienen del cliente (ignorar webhooks de mensajes enviados por el bot)
        if message_type == 'to_client':
            logger.debug(f"Ignorando mensaje saliente con type={message_type}")
            return JSONResponse(content={"status": True, "message": "Mensaje saliente ignorado"})
            
        # Only process incoming client messages
        if message_type != 'from_client':
            logger.debug(f"Ignorando mensaje con type={message_type} que no es from_client")
            return JSONResponse(content={"status": True, "message": "Mensaje del sistema ignorado"})
        
        # Verificar si este mensaje ya ha sido procesado (deduplicación)
        if processed_message_ids.contains(uid):
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
        # Handle None values in body
        if body is None:
            body = ""
            logger.debug("Message with None body detected, setting to empty string")


        # Get recent AI messages for this number to check for echoes
        recent_ai_messages = []
        if from_number in user_sessions:
            # Get last 3 AI messages from the conversation history
            for msg in user_sessions[from_number].history.messages[-6:]:  # Check last 6 messages
                if isinstance(msg, AIMessage):
                    recent_ai_messages.append(msg.content)
        
        # Check if this is our own message being reflected back
        if is_bot_generated_message(body, recent_ai_messages):
            logger.info(f"Detected echo of our own message: '{body[:50]}...' - Ignoring")
            return JSONResponse(content={"status": True, "message": "Echo message ignored"})
        
        # Check again specifically for image receipt messages
        if "[IMAGE_RECEIPT]" in body or (("he recibido" in body.lower() and "imagen" in body.lower()) and 
                                         ("total" in body.lower() or "puedes enviar" in body.lower())):
            logger.info(f"Detected image receipt message echo: '{body[:50]}...' - Ignoring")
            return JSONResponse(content={"status": True, "message": "Image receipt message ignored"})
        
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
            if not isinstance(coords, str):
                coords = str(coords)
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
                        # Verificar si hay un contexto de búsqueda de oficinas gubernamentales
                        # Esto puede ser determinado por mensajes previos del usuario o una variable de sesión
                        office_search_context = False
                        office_type = None
                        
                        # Si el usuario tiene una sesión activa, podemos verificar los mensajes recientes
                        if from_number in user_sessions:
                            recent_messages = user_sessions[from_number].history.messages[-5:]  # Últimos 5 mensajes
                            for msg in recent_messages:
                                if isinstance(msg, HumanMessage):
                                    msg_content = msg.content.lower()
                                    
                                    # Buscar referencias a oficinas gubernamentales
                                    if any(term in msg_content for term in ["registro civil", "acta", "nacimiento", "matrimonio", "defunción"]):
                                        office_search_context = True
                                        office_type = "registro_civil"
                                        break
                                        
                                    if any(term in msg_content for term in ["centro comunitario", "comunitario", "cursos", "talleres", "actividades"]):
                                        office_search_context = True
                                        office_type = "centro_comunitario"
                                        break
                                        
                                    # Buscar indicios de querer saber la más cercana
                                    if any(term in msg_content for term in ["cerca", "cercana", "cercano", "próxima", "próximo", "oficina"]):
                                        # Si no se ha identificado un tipo específico pero el usuario mencionó algo de cercanía
                                        if "registro" in msg_content or "acta" in msg_content:
                                            office_search_context = True
                                            office_type = "registro_civil"
                                            break
                                        elif "centro" in msg_content or "comunitario" in msg_content:
                                            office_search_context = True
                                            office_type = "centro_comunitario"
                                            break
                        
                        if office_search_context and office_type:
                            try:
                                result = await find_nearest_government_office(
                                    latitude=float(latitude),
                                    longitude=float(longitude),
                                    office_type=office_type
                                )
                                
                                if result.get("success", False):
                                    nearest = result.get("nearest_office", {})
                                    
                                    # Crear respuesta con la oficina más cercana
                                    office_type_name = "Registro Civil" if office_type == "registro_civil" else "Centro Comunitario"
                                    body = f"He encontrado el {office_type_name} más cercano a tu ubicación:\n\n"
                                    body += f"🏢 *{nearest.get('name', 'No disponible')}*\n"
                                    body += f"📍 Dirección: {nearest.get('address', 'No disponible')}\n"
                                    body += f"📞 Teléfono: {nearest.get('phone', 'No disponible')}\n"
                                    body += f"🕒 Horario: {nearest.get('schedule', 'No disponible')}\n"
                                    body += f"🚶 Distancia: {nearest.get('distance', 'No disponible')} km\n\n"
                                    
                                    # Añadir recomendaciones alternativas (las siguientes 2 más cercanas)
                                    all_offices = result.get("all_offices", [])
                                    if len(all_offices) > 1:
                                        body += "Otras opciones cercanas:\n\n"
                                        for i, office in enumerate(all_offices[1:3], 1):
                                            if isinstance(office, dict):  # Verificar que office sea un diccionario
                                                body += f"{i}. *{office.get('name', 'No disponible')}* - {office.get('distance', 'No disponible')} km\n"
                                                body += f"   📍 {office.get('address', 'No disponible')}\n"
                                    # IMPORTANTE: Enviar este mensaje directamente al usuario sin pasar por el LLM
                                    # Guardar el mensaje en la BD
                                    logger.debug(f"Guardando respuesta directa con información de oficina cercana: {body[:30]}...")
                                    assistant_message = Message(
                                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        senderName="Assistant",
                                        message=body,
                                        number=from_number,
                                        uid=uid,
                                        direction="outbound",
                                        mtype="text",
                                        source="whatsapp"
                                    )
                                    db.Insert(assistant_message)
                                    await manage_message_history(db, from_number)
                                    
                                    # Enviar mensaje directamente a través de Chat2Desk
                                    api_token = os.getenv("CHAT2DESK_API_TOKEN")
                                    chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                                    
                                    headers = {
                                        "Authorization": api_token,
                                        "Content-Type": "application/json"
                                    }
                                    
                                    data = {
                                        "client_id": client_id,
                                        "channel_id": channel_id,
                                        "transport": "wa_direct",
                                        "text": body
                                    }
                                    
                                    direct_response = requests.post(chat2desk_url, json=data, headers=headers)
                                    
                                    if direct_response.status_code == 200:
                                        logger.debug(f"Información de oficina cercana enviada exitosamente a Chat2Desk")
                                        # No continuar con el procesamiento normal del LLM
                                        return JSONResponse(content={"status": True, "message": "Respuesta directa enviada por Chat2Desk"})
                                    else:
                                        logger.error(f"Error al enviar mensaje directo a Chat2Desk: {direct_response.status_code} - {direct_response.text}")
                                        # Continuar con el flujo normal si falla el envío directo
                                else:
                                    body = f"Lo siento, tuve un problema al buscar la oficina más cercana. {result.get('error', '')}"
                            except Exception as e:
                                logger.error(f"Error al buscar oficina cercana: {str(e)}")
                                body = f"Lo siento, ocurrió un error al buscar oficinas cercanas. Por favor, intenta de nuevo más tarde."
                        else:
                            # Respuesta estándar para ubicación (mantener el comportamiento actual)
                            body = f"Ubicación recibida: {address}\nLatitud: {latitude}, Longitud: {longitude}"
                            
                            # Si hay un reporte en progreso, actualizar la ubicación
                            if from_number in report_sessions:
                                report_sessions[from_number]["location"] = address
                                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                            
                    except Exception as e:
                        logger.error(f"Error al procesar coordenadas: {str(e)}")
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
                previous = get_user_answer(from_number, "selection8") or ""
                updated_list = [url.strip() for url in previous.split(",") if url.strip()]
                updated_list.append(photo_url)
                new_value = ",".join(updated_list)
                save_user_answer(from_number, "selection8", new_value)
                logger.info(f"[{from_number}] Imagen añadida a selection8: {photo_url}")
                try:
                    # Analizar la imagen con rate limiting
                    image_description = await analyze_image_with_rate_limit(image_analysis_client, photo_url)
                    # Almacenar en la sesión de reporte
                    if from_number not in report_sessions:
                        report_sessions[from_number] = {
                            "images": [],
                            "image_descriptions": [],
                            "location": None,
                            "timestamp": datetime.now(pytz.timezone('America/Mexico_City'))
                        }
                    
                    # Añadir esta imagen al reporte en progreso - con verificación
                    if isinstance(photo_url, str) and (photo_url.startswith("http") or "storage.chat2desk.com" in photo_url):
                        # Inicializar session de reporte si no existe
                        if from_number not in report_sessions:
                            report_sessions[from_number] = {
                                "images": [],
                                "image_descriptions": [],
                                "location": None,
                                "timestamp": datetime.now(pytz.timezone('America/Mexico_City'))
            }
                        # Asegurarse de que la imagen no esté duplicada
                        if photo_url not in report_sessions[from_number]["images"]:
                            report_sessions[from_number]["images"].append(photo_url)
                            report_sessions[from_number]["image_descriptions"].append(image_description)
                            report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                            
                            logger.info(f"Imagen #{len(report_sessions[from_number]['images'])} añadida al reporte para {from_number}")
                        else:
                            logger.warning(f"Imagen duplicada ignorada: {photo_url[:50]}...")
                    else:
                        logger.error(f"URL de imagen inválida: {str(photo_url)[:50]}...")
                    
                    num_images = len(report_sessions[from_number]["images"])
                    la_foto = report_sessions[from_number]["image_descriptions"][0]
                    if num_images == 1:
                        body = f"{sender_name} he recibido tu imagen veo {la_foto}, y la he guardado para el reporte. Puedes enviar más imágenes."
                    else:
                        body = f"[Imagen_Recibida] He recibido otra imagen (tienes {num_images} en total). Puedes seguir enviando imágenes o finalizar cuando estés listo."
                    
                    logger.debug(f"Imagen añadida al reporte en progreso para {from_number}. Total: {num_images}")
                    
                    # Since this is an image-only message, we need to send our response right away
                    try:
                        # Store the bot's response in the database and conversation history
                        if from_number in user_sessions:
                            conversation_history = user_sessions[from_number].history
                            conversation_history.add_ai_message(body)
                        
                        # Create a message record
                        assistant_message = Message(
                            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            senderName="Assistant",
                            message=body,
                            number=from_number,
                            uid=uid,
                            direction="outbound",
                            mtype="text",
                            source="whatsapp"
                        )
                        db.Insert(assistant_message)
                        await manage_message_history(db, from_number)
                        
                        # Send the response to Chat2Desk
                        api_token = os.getenv("CHAT2DESK_API_TOKEN")
                        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                        
                        headers = {
                            "Authorization": api_token,
                            "Content-Type": "application/json"
                        }
                        
                        data = {
                            "client_id": client_id,
                            "channel_id": channel_id,
                            "transport": "wa_direct",
                            "text": body
                        }
                        
                        response = requests.post(chat2desk_url, json=data, headers=headers)
                        
                        if response.status_code == 200:
                            logger.debug(f"Respuesta de imagen enviada exitosamente a Chat2Desk")
                            return JSONResponse(content={"status": True, "message": "Respuesta de imagen enviada por Chat2Desk"})
                        else:
                            logger.error(f"Error al enviar respuesta de imagen a Chat2Desk: {response.status_code} - {response.text}")
                    except Exception as e:
                        logger.error(f"Error al enviar respuesta de imagen: {str(e)}")
                        return JSONResponse(content={"error": f"Error al enviar respuesta de imagen: {str(e)}"}, status_code=500)
                    
                except requests.RequestException as e:
                    logger.error(f"Error al descargar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero no se pudo descargar. Por favor, intenta enviarla de nuevo."
                except Exception as e:
                    logger.error(f"Error al analizar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero hubo un problema al analizarla. El equipo técnico ha sido notificado."
            else:
                body = "Se recibió una notificación de imagen, pero no se encontró la URL de la imagen."
                logger.warning("No se pudo obtener la URL de la imagen del formulario de datos.")

        elif body and from_number in report_sessions:
            detect_and_store_user_data(from_number, body)
            logger.debug(f"[{from_number}] Revisión anticipada de datos estructurados: '{body[:50]}...'")

        # Now let's fix the report finalization check in the WhatsApp endpoint
        elif body and from_number in report_sessions and report_sessions[from_number]["images"]:
            # El usuario ya ha enviado imágenes, este texto podría ser información del reporte
            
            # Log the message to help with debugging
            logger.debug(f"Processing potential report data for {from_number}: '{body[:50]}...'")
            
            # First, ensure this isn't a bot-generated message being echoed back
            is_bot_message = False
            
            # Check for specific image receipt markers
            if "[IMAGE_RECEIPT]" in body or ("he recibido" in body.lower() and "imagen" in body.lower()):
                is_bot_message = True
                logger.warning(f"Ignoring bot image receipt message: '{body[:50]}...'")
            
            # For other messages, check if they match recent bot messages
            if not is_bot_message and from_number in user_sessions:
                recent_messages = user_sessions[from_number].history.messages[-3:]  # Last 3 messages
                for msg in recent_messages:
                    if isinstance(msg, AIMessage) and (msg.content in body or body in msg.content):
                        is_bot_message = True
                        logger.warning(f"Message appears to be a bot message echo: '{body[:50]}...'")
                        break
            if not is_bot_message:
                detect_and_store_user_data(from_number, body)
            
            if is_bot_message:
                # Skip processing if this appears to be from the bot
                return JSONResponse(content={"status": True, "message": "Bot message echo ignored"})
            
            # Now check if this is providing location or requesting finalization
            is_location = any(keyword in body.lower() for keyword in ["ubicación", "dirección", "calle", "avenida", "colonia", "avenue", "numero", "número"])
            is_finalization = is_finalization_message(body, from_number)

            
            # Log the classification for debugging
            logger.debug(f"Message classification - Is location: {is_location}, Is finalization: {is_finalization}")
            
            if is_location:
                # Es información de ubicación
                report_sessions[from_number]["location"] = body
                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                body = f"Ubicación registrada: {body}. Para finalizar tu reporte con las imágenes que has enviado, avísame cuando estés listo."
            elif is_finalization:
                # Generate a unique request ID for this report finalization request
                request_id = f"{from_number}-{int(datetime.now().timestamp())}"
                logger.info(f"Report finalization request {request_id} received")
                
                # En lugar de procesar directamente, enviar un mensaje especial al modelo
                finalization_prompt = "El usuario quiere finalizar el reporte. " + \
                         "Por favor, verifica que has recopilado toda la información necesaria " + \
                         "(asunto, nombre, calle, número, colonia) y llama a la función save_client_selection " + \
                         "con los datos completos. Si falta algún dato, solicítalo antes de proceder."
                
                # Añadir este mensaje al historial como si fuera un mensaje del sistema
                if from_number in user_sessions:
                    conversation_history = user_sessions[from_number].history
                    conversation_history.add_ai_message(f"[SISTEMA: {finalization_prompt}]")

                # El usuario quiere finalizar el reporte
                images = report_sessions[from_number]["images"]
                descriptions = report_sessions[from_number]["image_descriptions"]

                if fotos_urls:
                    for foto in fotos_urls:
                        if foto not in images:
                            images.append(foto)
                            descriptions.append("Imagen adicional")  # Descripción genérica
                
                # Deduplicate images to ensure no duplicates
                unique_images = []
                unique_descriptions = []
                img_set = set()
                
                for i, img in enumerate(images):
                    if img not in img_set:
                        img_set.add(img)
                        unique_images.append(img)
                        if i < len(descriptions):
                            unique_descriptions.append(descriptions[i])
                
                logger.info(f"After deduplication: {len(unique_images)} of {len(images)} images remain")
                
                # Use the location stored in the report session or the current message as fallback
                user_location = report_sessions[from_number]["location"] or body or "ubicación no especificada"
                
                # Usar la función centralizada para procesar el reporte
                result = await process_and_save_report(from_number, user_location, unique_images, unique_descriptions)
                
                if result['status'] == 'in_progress':
                    body = result['message']
                elif result['status'] == 'duplicate':
                    body = result['message']
                elif result['status'] == 'no_images':
                    body = result['message']
                elif result['status'] == 'error':
                    body = f"Lo siento, hubo un error al finalizar tu reporte: {result['message']}. Por favor, intenta nuevamente."
                elif result['status'] == 'success':
                    # El reporte se creó exitosamente
                    folio = result['folio']
                    logger.info(f"Successfully created report with folio {folio} for request {request_id}")

                    mark_report_as_completed(from_number)
                    # Limpiar la sesión de reporte después de finalizar
                    if from_number in report_sessions:
                        del report_sessions[from_number]
                                            
                    # Importante: Construir un mensaje informativo que *NO* requiera acción adicional del usuario
                    image_text = f"con {len(unique_images)} imágenes " if unique_images else ""
                    body = f"Tu reporte ha sido generado con éxito. El número de folio para tu reporte es {folio}. Tu reporte {image_text}ha sido enviado al sistema. Agradecemos mucho tu colaboración. Estamos para servirte"
                    
                    # Verificar que el mensaje no esté vacío 
                    if not body or len(body.strip()) == 0:
                        body = f"Tu reporte ha sido generado exitosamente. Agradecemos tu colaboración. Estamos para servirte."

                    # Crear y guardar un mensaje de sistema explicando lo que ocurrió
                    img_count = f"que incluye {len(unique_images)} imágenes " if unique_images else ""
                    system_notification = Message(
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        senderName="System",
                        message=f"[SISTEMA: Se generó el reporte con folio {folio} {img_count}de la ubicación '{user_location}'. El reporte ha sido enviado al sistema.]",
                        number=from_number,
                        uid=f"system-{request_id}",
                        direction="system",
                        mtype="text",
                        source="whatsapp"
                    )
                    db.Insert(system_notification)

                    # IMPORTANTE: Ahora vamos a enviar este mensaje directamente a través de Chat2Desk
                    # para evitar que siga el flujo normal y cause una transferencia a humano
                    try:
                        # Guardar la respuesta en el historial y en la base de datos como mensaje del asistente
                        assistant_message = Message(
                            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            senderName="Assistant",
                            message=body,
                            number=from_number,
                            uid=f"success-report-{request_id}",
                            direction="outbound",
                            mtype="text",
                            source="whatsapp"
                        )
                        db.Insert(assistant_message)
                        await manage_message_history(db, from_number)
                        
                        # Enviar directamente el mensaje a través de Chat2Desk
                        api_token = os.getenv("CHAT2DESK_API_TOKEN")
                        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                        
                        headers = {
                            "Authorization": api_token,
                            "Content-Type": "application/json"
                        }
                        
                        data = {
                            "client_id": client_id,
                            "channel_id": channel_id,
                            "transport": "wa_direct",
                            "text": body
                        }
                        
                        response = requests.post(chat2desk_url, json=data, headers=headers)
                        
                        if response.status_code == 200:
                            logger.debug(f"Mensaje de finalización enviado directamente a través de Chat2Desk")
                        else:
                            logger.error(f"Error al enviar mensaje directo a Chat2Desk: {response.status_code} - {response.text}")
                    except Exception as e:
                        logger.error(f"Error al enviar mensaje de finalización directo: {str(e)}")
                    
                    # IMPORTANTE: Devolver un resultado sin mensaje de texto para evitar el procesamiento posterior
                    # Esto evitará que el sistema envíe otro mensaje o confunda el texto de respuesta como entrada
                    return {
                        'status': 'success',
                        'message': "",  # Vacío para evitar procesamiento posterior
                        'folio': folio
                    }

                    
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
            image_description=image_description if 'image_description' in locals() else "No se ha recibido ninguna imagen",
            fotos=(report_sessions[from_number]["images"] if from_number in report_sessions and report_sessions[from_number]["images"] else "")
        )
        # Añadir instrucción para evitar generación automática de reportes
        # if from_number in report_sessions and report_sessions[from_number]["images"]:
        #     system_prompt += "\n\nINSTRUCCIÓN IMPORTANTE: NO crees ningún reporte ni menciones folios en tu respuesta. El usuario debe decir EXPLÍCITAMENTE 'Crear reporte' para que se genere. No inventes folios ni digas que has creado un reporte a menos que yo te confirme que el reporte ya fue generado."

        # llm_service = OpenAIService(
        #     config=config,
        #     api_key=os.getenv("OPENAI_API_KEY"),
        #     system=system_prompt,
        #     function_manager=function_manager
        # )

        llm_service = DeepSeekService(
            config=config,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
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
    current_time = datetime.now().timestamp()

    # Verificar si ya se envió una respuesta a este número recientemente 
    if from_number in last_response_time:
        time_since_last_response = current_time - last_response_time[from_number]
        # Si han pasado menos de 5 segundos desde la última respuesta, no enviar otra
        if time_since_last_response < 5:  # 5 segundos como tiempo mínimo entre respuestas
            logger.info(f"Evitando respuesta duplicada para {from_number} (solo han pasado {time_since_last_response:.2f} segundos)")
            return JSONResponse(content={"status": True, "message": "Evitada respuesta duplicada"})

    # Actualizar el tiempo de la última respuesta
    last_response_time[from_number] = current_time

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
                
                # Add a log message suggesting the human agent to send the takeover message
                response_content = "Gracias por tu paciencia. Te estamos transfiriendo a un agente humano que te atenderá en breve."
                
                # Execute the actual transfer - CHANGE FROM ASYNC TO SYNC
                phone_number = from_number
                try:
                    # Extract group_id if specified
                    group_id = 1772
                    import re
                    group_match = re.search(r'transfer_to_group\(.*?(\d+).*?\)', response_content)
                    if group_match:
                        group_id = int(group_match.group(1))
                    
                    # Execute the transfer function SYNCHRONOUSLY
                    result = await transfer_to_group(phone_number, group_id, reason="Transferencia automática")
                    logger.info(f"Transfer result: {result}")

                    # Add a notification in the database about the transfer
                    transfer_note = Message(
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        senderName="System",
                        message=f"[SYSTEM] Se ha iniciado transferencia a agente humano. Se recomienda enviar: '{HUMAN_TAKEOVER_MESSAGE}'",
                        number=from_number,
                        uid=f"transfer-note-{datetime.now().timestamp()}",
                        direction="system",
                        mtype="text",
                        source="whatsapp"
                    )
                    db.Insert(transfer_note)

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
    async def remove_from_transferred(number, delay_seconds):
        await asyncio.sleep(delay_seconds)
        if number in transferred_numbers:
            transferred_numbers.remove(number)
            logger.debug(f"Removed {number} from transferred numbers list after {delay_seconds} seconds")

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

            if phone_number in report_sessions:
                del report_sessions[phone_number]
            logger.debug(f"Sesión de reporte de {phone_number} finalizada por despedida.")
                
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
        channel_id = 43388  # Valor fijo conocido para el canal de WhatsApp
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