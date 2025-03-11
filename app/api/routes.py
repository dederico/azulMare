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
from langchain.schema import HumanMessage, AIMessage, SystemMessage
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
        
        logger.debug(f"Datos recibidos: chat_id={chat_id}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, message_type={message_type}, uid={uid}")

        # Variables para ubicación, imagen y audio
        address = None
        latitude, longitude = None, None
        photo_url = None
        audio_url = None

        # Verificación del tipo de contenido en el mensaje
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
    session.update_activity()  # Actualiza la marca de actividad
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