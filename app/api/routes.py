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

load_dotenv()
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
from langchain.schema import HumanMessage, AIMessage
from app.services.stt.stt_service import STTService
from app.services.stt.media_transcriber import TranscribeOGG
from twilio.base.exceptions import TwilioRestException

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")
CHAT2DESK_API_TOKEN = "5d211f3aeb829cc4149ebfc24d1a6f"

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
        system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date2=date_string, now=hour, folio=folio),
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
INACTIVITY_THRESHOLD = 5 * 60

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
    de alerta por Twilio y se elimina la sesión.
    """
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        now = datetime.now(pytz.timezone('America/Mexico_City'))
        for number, session in list(user_sessions.items()):
            elapsed = (now - session.last_active).total_seconds()
            if elapsed > INACTIVITY_THRESHOLD:
                try:
                    twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                    disconnection_message = "Se ha desconectado la sesión por inactividad."
                    # Asegúrate de tener configurado el número de WhatsApp de Twilio en TWILIO_WHATSAPP_NUMBER
                    twilio_client.messages.create(
                        body=disconnection_message,
                        from_="whatsapp:" + os.getenv("TWILIO_WHATSAPP_NUMBER"),
                        to="whatsapp:" + number
                    )
                    logger.debug(f"Sesión de {number} desconectada por inactividad.")
                except Exception as e:
                    logger.error(f"Error enviando mensaje de desconexión para {number}: {str(e)}")
                del user_sessions[number]

# ------------------------------
# Función de ciclo de vida (lifespan)
# ------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: se lanza la tarea de verificación de inactividad
    asyncio.create_task(check_inactivity())
    yield
    # Shutdown: se puede agregar lógica de limpieza si se requiere
app = FastAPI(lifespan=lifespan)

router = APIRouter()

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
        payload = await request.json()
        logger.debug(f"Payload recibido: {payload}")
        
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        message_type = payload.get('type', 'text')
        uid = payload.get('message_id')

        logger.debug(f"Datos extraídos: chat_id={chat_id}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, message_type={message_type}")

        mexico_tz = pytz.timezone('America/Mexico_City')
        current_datetime = datetime.now(mexico_tz)
        date_string = current_datetime.strftime("%Y-%m-%d")
        hour = current_datetime.strftime("%I:%M:%S %p")
        folio = await save_client_selection(from_number, "", "", "", "", "", "", "", "")

        llm_service = OpenAIService(
            config=config,
            api_key=OPENAI_API_KEY,
            system=system_message.format(date2=date_string, now=hour, folio=folio),
            function_manager=function_manager
        )
        
        # Variables para ubicación e imagen
        address = None
        latitude, longitude = None, None
        
        if message_type == "location":
            # Procesar mensaje de ubicación si es necesario
            pass
        elif message_type == "audio":
            # Procesar mensaje de audio si es necesario
            pass
        elif message_type == "image":
            # Procesar mensaje de imagen si es necesario
            pass
            
    except Exception as e:
        logger.error(f"Error al procesar el payload: {str(e)}")
        return JSONResponse(content={"error": "Error al procesar el payload"}, status_code=400)

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
        messages_db = db.Search(Message(number=from_number, source="whatsapp"), order='asc', limit=50) or []
        for msg in messages_db:
            role = "assistant" if msg.direction == "outbound" else "user"
            if role == "user":
                conversation_history.add_user_message(msg.message)
            else:
                conversation_history.add_ai_message(msg.message)
            logger.debug(f"Mensaje recuperado para historial: rol={role}, contenido={msg.message}")
    except Exception as e:
        logger.error(f"Error al recuperar mensajes históricos de la base de datos: {str(e)}")

    # Agregar mensaje de usuario al historial y guardar en la base de datos
    conversation_history.add_user_message(body)
    user_message = Message(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        senderName=sender_name,
        message=body,
        number=from_number,
        uid=uid,
        direction="inbound",
        mtype=message_type,
        source="Whatsapp",
        latitude=latitude,
        longitude=longitude
    )
    db.Insert(user_message)
    
    try:
        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(
            customer_name=sender_name,
            call_sid=uid,
            date2=date_string,
            now=hour,
            folio=folio,
            phone_number=from_number
        )
        
        user_input = "\n".join([f"Human: {msg.content}" if isinstance(msg, HumanMessage) else f"AI: {msg.content}" for msg in conversation_history.messages])
        user_input += f"\nHuman: {body}"

        logger.debug(f"Prompt generado: {user_input}")

        # Generar la respuesta del modelo
        model_response = llm_service.generate_response(user_input=user_input)
        response_content = ""
        async for response in model_response:
            response_content += str(response)
        logger.debug(f"Respuesta del modelo: {response_content}")

        if not response_content.strip():
            logger.warning("La respuesta del modelo está vacía. Usando un mensaje predeterminado.")
            response_content = "Lo siento, no pude generar una respuesta en este momento. Por favor, intenta de nuevo o contacta a un agente humano para asistencia."

        conversation_history.add_ai_message(response_content)
        assistant_message = Message(
            time=current_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            senderName="Assistant",
            message=response_content,
            number=from_number,
            uid=uid,
            direction="outbound",
            mtype=message_type,
            source="Whatsapp"
        )
        db.Insert(assistant_message)

        client_id = payload.get('client', {}).get('id')
        print("client_id",client_id) # Extrae el client_id del payload
        channel_id = payload.get("channel_id") 
        print("channel_id",channel_id) # Extrae el channel_id del payload
        robot_answer = assistant_message.message
        print("response_content",assistant_message.message) # Imprime la respuesta generada
        if not client_id or not channel_id:
            logger.error("Error: client_id o channel_id no están definidos.")
            return JSONResponse(content={"error": "No se pudo obtener client_id o channel_id"}, status_code=400)

        chat2desk_response = await send_chat2desk_message(client_id, channel_id, robot_answer)

        if chat2desk_response.status_code != 200:
            logger.error(f"Error al enviar mensaje a través de Chat2Desk: {chat2desk_response.text}")
            return JSONResponse(content={"error": "Error al enviar mensaje"}, status_code=500)

        logger.info(f"Mensaje enviado exitosamente a {from_number}")
        return JSONResponse(content={"message": "Mensaje procesado y enviado con éxito"}, status_code=200)

    except Exception as e:
        logger.error(f"Error al procesar el mensaje: {str(e)}")
        return JSONResponse(content={"error": "Error interno del servidor"}, status_code=500)

async def send_chat2desk_message(client_id, channel_id, response_content):
    if not client_id:
        logger.error("client_id es None o vacío")
        return None
    if not channel_id:
        logger.error("channel_id es None o vacío")
        return None
    if not response_content:
        logger.error("response_content es None o vacío")
        return None
    
    url = "https://api.chat2desk.com.mx/v1/messages"
    headers = {
        "Authorization": os.getenv("CHAT2DESK_API_TOKEN"),  # Reemplaza 'your_api_token' con tu token real de la API
        "Content-Type": "application/json"
    }

    # Asumiendo que el "wa_direct" es el transporte correcto para WhatsApp
    data = {
        "client_id": client_id,
        "channel_id": channel_id,
        "transport": "wa_direct",  # Indicando que el transporte es WhatsApp directo
        "text": response_content  # El mensaje de texto que se enviará
    }

    try:
        response = await httpx.post(url, json=data, headers=headers)
        return response
    except Exception as e:
        logger.error(f"Error al enviar mensaje a Chat2Desk: {str(e)}")
        raise e

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