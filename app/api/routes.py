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
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")

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
        payload = await request.json()  # Ahora recibimos el payload como un JSON
        print(f"Payload recibido: {payload}")
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        message_type = payload.get('type', '')  # El campo type no será siempre 'text'
        uid = payload.get('message_id')
        channel_id = payload.get('channel_id')
        client_id = payload.get('client_id')
        logger.debug(f"Datos recibidos: chat_id={chat_id}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, message_type={message_type}, uid={uid}")

        # Variables para ubicación, imagen y audio
        address = None
        latitude, longitude = None, None
        photo_url = None
        audio_url = None

        # Verificación del tipo de mensaje recibido
        if message_type == 'from_client':
            # Este tipo indica que es un mensaje para el cliente
            body = payload.get('text', '')
        
        elif payload.get("coordinates"):
            # Procesamiento de ubicación
            latitude, longitude = payload.get("coordinates").split(",")
            try:
                # Convertir la latitud y longitud a dirección
                address = await latlong_to_address(float(latitude), float(longitude))
                body = f"Ubicación recibida: {address}\nLatitud: {latitude}, Longitud: {longitude}"
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
                        model="gpt-4o",  # Asegúrate de usar el modelo correcto
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
                    body = f"Imagen recibida. Descripción: {image_description}"
                    logger.debug(f"Descripción de la imagen: {image_description}")
                except requests.RequestException as e:
                    logger.error(f"Error al descargar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero no se pudo descargar. Por favor, intenta enviarla de nuevo."
                except Exception as e:
                    logger.error(f"Error al analizar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero hubo un problema al analizarla. El equipo técnico ha sido notificado."
            else:
                body = "Se recibió una notificación de imagen, pero no se encontró la URL de la imagen."
                logger.warning("No se pudo obtener la URL de la imagen del formulario de datos.")
            
    except KeyError as e:
        logger.error(f"Falta el parámetro requerido: {e}")
        return JSONResponse(content={"error": f"Falta el parámetro {str(e)}"}, status_code=400)

    # Crear o actualizar la sesión del usuario
    if from_number not in user_sessions:
        logger.debug(f"Creando nueva sesión para el usuario: {from_number}")
        user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
    session = user_sessions[from_number]
    session.update_activity()  # Actualiza la marca de actividad
    conversation_history = session.history

    # Recuperar mensajes históricos desde la base de datos y agregarlos al historial
    try:
        logger.debug(f"Recuperando mensajes históricos para el número: {from_number}")
        
        # Obtener tanto mensajes inbound como outbound (de usuario y asistente)
        messages_db = db.Search(Message(number=from_number, source="whatsapp"), order='desc', limit=50) or []

        # Solo añadir al historial si no es un mensaje duplicado
        for msg in messages_db:
            role = "assistant" if msg.direction == "outbound" else "user"
            
            # Si el mensaje del usuario no está en el historial, añadirlo
            if role == "user" and msg.message not in [m['content'] for m in conversation_history.messages]:
                conversation_history.add_user_message(msg.message)
                logger.debug(f"Mensaje recuperado para historial (usuario): {msg.message}")
            
            # Si el mensaje del asistente no está en el historial, añadirlo
            elif role == "assistant" and msg.message not in [m['content'] for m in conversation_history.messages]:
                conversation_history.add_ai_message(msg.message)
                logger.debug(f"Mensaje recuperado para historial (asistente): {msg.message}")
            
    except Exception as e:
        logger.error(f"Error al recuperar mensajes históricos de la base de datos: {str(e)}")


    # Agregar mensaje de usuario al historial y guardar en la base de datos
    conversation_history.add_user_message(body)
    user_message = Message(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        senderName="User",
        message=body,
        number=from_number,
        uid=uid,
        direction="inbound",  # Aseguramos que sea un mensaje de usuario (inbound)
        mtype="text",  # Aquí "text" es el tipo general de mensaje
        source="Whatsapp",
        latitude=latitude,  # Guardar latitud si está disponible
        longitude=longitude  # Guardar longitud si está disponible
    )
    logger.debug(f"Ingresando mensaje del usuario: {user_message.message} con dirección {user_message.direction}")
    db.Insert(user_message)
    
    mexico_tz = pytz.timezone('America/Mexico_City')
    current_datetime = datetime.now(mexico_tz)
    date_string = current_datetime.strftime("%Y-%m-%d")
    hour = current_datetime.strftime("%I:%M:%S %p")
    folio = await save_client_selection(from_number, "", "", "", "", "", "", "", "")
    
    try:
        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(
            customer_name=sender_name,
            call_sid=uid,
            date2=date_string,
            now=hour,
            folio=folio,
            address=address if 'address' in locals() else "No he recibido ubicación",
            image_description=image_description if 'image_description' in locals() else "No se ha recibido ninguna imagen"
        )

        llm_service = OpenAIService(
            config=config,
            api_key=os.getenv("OPENAI_API_KEY"),
            system=system_prompt,
            function_manager=function_manager
        )

        # Procesar la imagen si está disponible
        if 'image_description' in locals() and image_description:
            image_message = f"[Imagen recibida. Descripción: {image_description}]"
            conversation_history.add_user_message(image_message)
            conversation_history.add_ai_message("Porfavor, analiza y comenta sobre la imagen en tu proxima respuesta.")

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
            number=from_number,
            uid=uid,
            direction="outbound",  # Mensaje del asistente
            mtype="text",  # Se mantiene como "text" en el tipo de mensaje
            source="Whatsapp"
        )
        db.Insert(assistant_message)

    except Exception as e:
        logger.error(f"Error al generar la respuesta del modelo: {str(e)}")
        return JSONResponse(content={"error": "Error al generar respuesta"}, status_code=500)
    
    api_token = os.getenv("CHAT2DESK_API_TOKEN")
    # Enviar la respuesta por Chat2Desk
    try:
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"  # URL de Chat2Desk
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": response_content
        }
        response = requests.post(chat2desk_url, json=data, headers=headers)
        
        print("Esto estoy enviando a Chat2Desk: ",response)
        
        if response.status_code == 200:
            logger.debug(f"Mensaje enviado con éxito a Chat2Desk: {response_content}")
            content = {"status": True, "message": "Respuesta enviada por Chat2Desk"}
        else:
            logger.error(f"Error al enviar mensaje a Chat2Desk: {response.text}")
            content = {"status": False, "error": "Error al enviar mensaje a Chat2Desk"}

    except requests.RequestException as e:
        logger.error(f"Error al enviar mensaje a Chat2Desk: {str(e)}")
        content = {"status": False, "error": f"No se pudo enviar el mensaje a Chat2Desk: {str(e)}"}

    return JSONResponse(content=content)


# def add_message_to_history(role: str, message_content: str, conversation_history):
#     """Función para agregar mensajes al historial"""
#     if role == "user":
#         conversation_history.add_user_message(message_content)
#     else:
#         conversation_history.add_ai_message(message_content)

# import os
# import httpx
# import logging

# logger = logging.getLogger(__name__)

# async def send_chat2desk_message(client_id, channel_id, response_content):
#     logger.debug(f"Intentando enviar mensaje: client_id={client_id}, channel_id={channel_id}, response_content={response_content}")

#     if not client_id:
#         logger.error("client_id es None o vacío")
#         return None
#     if not channel_id:
#         logger.error("channel_id es None o vacío")
#         return None
#     if not response_content:
#         logger.error("response_content es None o vacío")
#         return None

#     if not isinstance(response_content, str):
#         logger.warning(f"response_content no es una cadena: {type(response_content)}. Intentando convertir a string.")
#         try:
#             response_content = str(response_content)
#         except Exception as e:
#             logger.error(f"No se pudo convertir response_content a string: {e}")
#             return None

#     api_token = os.getenv("CHAT2DESK_API_TOKEN")
#     if not api_token:
#         logger.error("El token de API de Chat2Desk no está configurado.")
#         return None

#     url = "https://api.chat2desk.com.mx/v1/messages"
#     headers = {
#         "Authorization": api_token,
#         "Content-Type": "application/json"
#     }

#     data = {
#         "client_id": client_id,
#         "channel_id": channel_id,
#         "transport": "wa_direct",
#         "text": response_content
#     }

#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.post(url, json=data, headers=headers, timeout=10)

#         if response is None:
#             logger.error("No se recibió respuesta de Chat2Desk.")
#             return None
#         if response.text is None:
#             logger.error("response.text es None, no se puede procesar.")
#             return None

#         logger.info(f"Respuesta de Chat2Desk: {response.status_code} - {response.text}")
#         return response
#     except httpx.RequestError as e:
#         logger.error(f"Error en la solicitud HTTP a Chat2Desk: {str(e)}")
#         return None
#     except Exception as e:
#         logger.error(f"Error inesperado al enviar mensaje: {str(e)}")
#         return None


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