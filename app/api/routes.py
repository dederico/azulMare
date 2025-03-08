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
    
    try:
        # Configuración de base de datos y demás servicios
        db = LocalStorage()
        config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
        function_manager = FunctionManager(registered_functions)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Obtener el payload JSON
        payload = await request.json()
        logger.debug(f"Payload recibido: {payload}")

        # Extraer información relevante del payload
        message_id = payload.get("message_id")
        text = payload.get("text")
        client_id = payload.get("client_id")
        client_info = payload.get("client", {})
        phone = client_info.get("phone")
        sender_name = client_info.get("name")
        channel_id = payload.get("channel_id")
        
        # Manejar diferentes tipos de contenido
        message_type = "text"
        if payload.get("coordinates"):
            message_type = "location"
            text = f"Ubicación: {payload['coordinates']}"
        elif payload.get("audio"):
            message_type = "audio"
            text = "Audio recibido"
        elif payload.get("photo"):
            message_type = "image"
            text = "Imagen recibida"

        # Crear o actualizar la sesión del usuario
        if phone not in user_sessions:
            user_sessions[phone] = ChatMessageHistory()
        conversation_history = user_sessions[phone]

        # Guardar el mensaje en la base de datos
        mexico_tz = pytz.timezone('America/Mexico_City')
        current_datetime = datetime.now(mexico_tz)
        
        user_message = Message(
            time=current_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            senderName=sender_name,
            message=text,
            number=phone,
            uid=str(message_id),
            direction="inbound",
            mtype=message_type,
            source="Whatsapp"
        )
        db.Insert(user_message)

        date_string = current_datetime.strftime("%Y-%m-%d")
        hour = current_datetime.strftime("%I:%M:%S %p")
        folio = await save_client_selection(message_id, "", "", "", "", "", "", "", "")

        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(
            customer_name=sender_name,
            call_sid=message_id,
            date2=date_string,
            now=hour,
            folio=folio
        )

        llm_service = OpenAIService(
            config=config,
            api_key=os.getenv("OPENAI_API_KEY"),
            system=system_prompt,
            function_manager=function_manager
        )

        # Formatear el historial de mensajes para el modelo
        formatted_history = [
            {"role": "user", "content": message.content} if isinstance(message, HumanMessage)
            else {"role": "system", "content": message.content} if isinstance(message, AIMessage)
            else {"role": "assistant", "content": message.content}
            for message in conversation_history.messages
        ]
        logger.debug(f"Historial formateado para el modelo: {formatted_history}")

        # Convertir formatted_history en un solo string para user_input
        user_input = "\n".join(f"{msg['role']}: {msg['content']}" for msg in formatted_history)
        logger.debug(f"Input concatenado para generate_response: {user_input}")

        # Generar la respuesta del modelo usando el string completo de user_input
        model_response = llm_service.generate_response(user_input=user_input)
        response_content = ""
        async for response in model_response:
            response_content += str(response)
        logger.debug(f"Respuesta parcial: {response_content}")

        if isinstance(response_content, list):
            response_content = " ".join([str(item) for item in response_content])
        elif not isinstance(response_content, str):
            response_content = str(response_content)

        conversation_history.add_ai_message(response_content)
            
        assistant_message = Message(
                time=current_datetime,
                senderName="Assistant",
                message=response_content,
                number=phone,
                uid=message_id,
                direction="outbound",
                mtype=message_type,
                source="Whatsapp"
        )
        db.Insert(assistant_message)

        # Enviar la respuesta a través de la API de Chat2Desk
        chat2desk_api_url = "https://api.chat2desk.com.mx/v1/messages"
        chat2desk_api_token = "5d211f3aeb829cc4149ebfc24d1a6f"
        
        chat2desk_payload = {
            "client_id": client_id,
            "type": "autoreply",
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": assistant_message
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                chat2desk_api_url,
                json=chat2desk_payload,
                headers={"Authorization": chat2desk_api_token}
            )

        if response.status_code == 200:
            logger.info("Mensaje enviado exitosamente a través de Chat2Desk")
        else:
            logger.error(f"Error al enviar mensaje a través de Chat2Desk: {response.text}")

        return JSONResponse(content={"status": "success", "message": "Mensaje procesado y respondido correctamente"})

    except Exception as e:
        logger.error(f"Error al procesar el mensaje de WhatsApp: {str(e)}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@router.post("/amd_detect")
async def amd_detect(request: Request):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    body_bytes = await request.body()
    body_str = body_bytes.decode()
    parsed_body = parse_qs(body_str)

    answered_by = parsed_body["AnsweredBy"][0]
    if answered_by not in ["human", "unknown"]:
        call_sid = parsed_body["CallSid"][0]
        client = Client(account_sid, auth_token)
        client.calls(call_sid).update(status="completed")

        db = LocalStorage()
        call = db.Search(Call(callUid = call_sid), True)
        if call:
            call.callStatus = "AMD"
            db.Update(call)

            hooks = Hooks()
            config = { c.name : c.value for c in db.GetAll(Config) }
            for hook in hooks.Get(True):
                if hook["type"] == "POST_CALL":
                    logger.debug("Hook found for call executing")
                    hook["function"](call, config)

        logger.warning(f"Machine - {answered_by} detected for: {call_sid}")


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


@router.post("/make_call")
async def make_call(request: Request):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    host = os.getenv("HOSTNAME")
    number = os.getenv("NUMBER")

    credentials = f"{account_sid}:{auth_token}"
    token = base64.b64encode(credentials.encode()).decode()

    payload_params = {
        "MachineDetection": "Enable",
        "AsyncAmd": "true",
        "Url": f"{host}/",
        "AsyncAmdStatusCallback": f"{host}/amd_detect",
        "To": "+573134506576",
        "From": number,
    }

    payload = urllib.parse.urlencode(payload_params)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {token}",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=payload) as response:
            try:
                response.raise_for_status()
                r = await response.text()
                logger.info(r)
            except Exception as e:
                logger.warning(f"Call failed with error: {e}")


# ---------------------
# Definición de la aplicación FastAPI
# ---------------------
app = FastAPI(lifespan=lifespan)
app.include_router(router)