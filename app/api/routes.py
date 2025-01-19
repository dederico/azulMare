import base64
import aiohttp
import logging
import urllib.parse
import os
import json
from io import StringIO
from dotenv import load_dotenv
from fastapi.responses import JSONResponse



# load_dotenv()
load_dotenv(override=True)
from fastapi import APIRouter, Request, Response, WebSocket, HTTPException
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
from app.services.functions.implementations.identify import get_customer_identity
from app.services.functions.implementations.date import get_current_date
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import HumanMessage, AIMessage
from app.services.stt.stt_service import STTService
from app.services.stt.media_transcriber import TranscribeOGG

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")

router = APIRouter()
# Historial en memoria para una conversación dinámica
user_histories = {}

@router.post("/")
async def post(request: Request):
    response = VoiceResponse()
    host = request.headers.get("host")
    connect = Connect()
    logger.info(f"wss://{host}/stream")
    connect.stream(url=f"wss://{host}/stream")
    response.append(connect)
    text = response.to_xml()
    logger.debug(text)
    return Response(content=text, media_type="text/xml")


@router.websocket("/stream")
async def websocket_endpoint(ws: WebSocket):
    db = LocalStorage()
    config = { conf.name: conf.getval() for conf in db.GetAll(Config) }
    logger.info(f"config {config}")
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
            callSource = "Layer7",
            callType = "IP",
            callDirection = "IN_COMING",
            callStatus = "IN_PROGRESS",
            callNumber = "Not Available",
            callUid = websocket_handler.call_sid
        )
        call = db.Insert(call)

    # Format the date as a string
    date_string = now.strftime("%Y-%m-%d")

    current_date = await get_current_date()

    # Get call SID and customer identity
    call_sid = websocket_handler.call_sid
    customer_identity = await get_customer_identity(call_sid)
    call.callerName = customer_identity
    context = websocket_handler.initial_data

    logger.debug("Initializing LLM service for the new call")
    llm_service = OpenAIService(
        config=config,
        api_key=OPENAI_API_KEY,
        system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date2=date_string, now=now, date=current_date, context=context),
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

@router.post("/whatsapp")
async def whatsapp(request: Request):
    logger.debug("Iniciando procesamiento del mensaje de WhatsApp.")
    # Configuración de base de datos
    db = LocalStorage()
    args = request.query_params
    config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
    function_manager = FunctionManager(registered_functions)

    try:
        form_data = await request.form()
        toN = form_data.get("To").split(":")[1]
        sender_name = form_data.get("ProfileName")
        body = form_data.get("Body")
        from_number = form_data.get("From").split(":")[1]
        wa_id = form_data.get("WaId")
        message_type = form_data.get("MessageType")
        uid = form_data.get("SmsMessageSid")

        logger.debug(f"Datos recibidos: toN={toN}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, wa_id={wa_id}, message_type={message_type}")
        
        # Verificar si el mensaje incluye coordenadas de ubicación
        latitude, longitude = None, None
        if message_type == "location":
            latitude = form_data.get("Latitude")
            longitude = form_data.get("Longitude")
            body = f"Ubicación recibida: Latitud {latitude}, Longitud {longitude}"
            logger.debug(f"Mensaje con ubicación: latitude={latitude}, longitude={longitude}")

        # Verificar si el mensaje incluye un audio
        elif message_type == "audio":
            body = TranscribeOGG(form_data.get("MediaUrl0"), config["language"])
            logger.debug(f"Audio transcrito: {body}")

            
    except KeyError as e:
        logger.error(f"Falta el parámetro requerido: {e}")
        return JSONResponse(content={"error": f"Falta el parámetro {str(e)}"}, status_code=400)

    # Crear el historial de conversación en memoria para el usuario si no existe
    if from_number not in user_histories:
        logger.debug(f"Creando nuevo historial de conversación para el usuario: {from_number}")
        user_histories[from_number] = ChatMessageHistory()

    conversation_history = user_histories[from_number]

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

    # Agregar mensaje de usuario al historial y guardar en base de datos
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
        latitude=latitude,  # Guardar latitud si está disponible
        longitude=longitude  # Guardar longitud si está disponible
    )
    db.Insert(user_message)

    # Configurar el LLM con el historial
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(
            customer_name=sender_name,
            call_sid=uid,
            date2=current_date,
            now=datetime.now(),
            date=current_date
        )

        llm_service = OpenAIService(
            config=config,
            api_key=OPENAI_API_KEY,
            system=system_prompt,
            function_manager=function_manager
        )
        
        # Formatear el historial de mensajes para el modelo
        formatted_history = [
            {"role": "user", "content": message.content} if isinstance(message, HumanMessage)
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
            time=current_date,
            senderName="Assistant",
            message=response_content,
            number=from_number,
            uid=wa_id,
            direction="outbound",
            mtype=message_type,
            source="Whatsapp"
        )
        db.Insert(assistant_message)

    except Exception as e:
        logger.error(f"Error al generar la respuesta del modelo: {str(e)}")
        return JSONResponse(content={"error": "Error al generar respuesta"}, status_code=500)

    # Enviar la respuesta por WhatsApp usando Twilio
    try:
        twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        twilio_client.messages.create(
            body=response_content,
            from_="whatsapp:" + toN,
            to="whatsapp:" + from_number
        )
        logger.debug(f"Mensaje enviado con éxito a WhatsApp: {response_content}")
        content = {"status": True, "message": "Respuesta enviada por WhatsApp"}
    except Exception as e:
        logger.error(f"Error al enviar mensaje con Twilio: {str(e)}")
        content = {"status": False, "error": f"No se pudo responder al mensaje de WhatsApp: {str(e)}"}

    return JSONResponse(content=content)

# @router.post("/whatsapp")
# async def whatsapp(request: Request):
#     db = LocalStorage()
#     config = { conf.name: conf.getval() for conf in db.GetAll(Config) }

#     # Obtener los parámetros de la URL
#     args = request.query_params
#     try:
#         toN = args.get("To")
#         if toN:
#             toN = toN.split(":")[1]
#         else:
#             logger.error("El campo 'To' no está presente en los parámetros")
#             return JSONResponse(content={"error": "El campo 'To' es obligatorio"}, status_code=400)

#         sender_name = args["ProfileName"]
#         body = args["Body"]
#         from_number = args["From"].split(":")[1]
#         wa_id = args["WaId"]
#     except KeyError as e:
#         logger.error(f"Falta el parámetro requerido: {e}")
#         return JSONResponse(content={"error": f"Falta el parámetro {str(e)}"}, status_code=400)

#     # Crear el mensaje actual
#     message = Message(
#         time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#         senderName=sender_name,
#         message=body,
#         number=from_number,
#         uid=wa_id,
#         direction="inbound",
#         mtype=args["MessageType"].split("/")[0],
#         source="Whatsapp"
#     )

#     # Recuperar mensajes históricos de la conversación
#     try:
#         messages = db.Search(Message(number=message.number, source="whatsapp"), order='asc', limit=50) or []
#         logger.debug(f"Mensajes recuperados para {message.number}: {[m.message for m in messages]}")
#     except Exception as e:
#         logger.error(f"Error al recuperar mensajes históricos: {str(e)}")
#         messages = []
    
#     # Confirmar que estamos construyendo la conversación histórica
#     conversation_history = []
#     for m in messages:
#         role = "assistant" if m.direction == "outbound" else "user"
#         conversation_history.append({"role": role, "content": m.message})
#         logger.debug(f"Mensaje agregado al historial: rol={role}, contenido={m.message}")

#     # Configurar el LLM con la conversación histórica
#     current_date = await get_current_date()
#     function_manager = FunctionManager(registered_functions)
#     now = datetime.now()

#     try:
#         llm_service = OpenAIService(
#             config=config,
#             api_key=OPENAI_API_KEY,
#             system=system_message.format(customer_name=message.senderName, call_sid=message.uid, date2=current_date, now=now, date=current_date),
#             function_manager=function_manager
#         )
#     except Exception as e:
#         logger.error(f"Error al configurar el servicio OpenAI: {str(e)}")
#         return JSONResponse(content={"error": "Error al configurar el servicio de inteligencia artificial"}, status_code=500)

#     # Añadir cada mensaje del historial a la sesión del LLM
#     for entry in conversation_history:
#         llm_service.add_to_conversation(entry["role"], entry["content"])

#     # Generar respuesta y enviar por WhatsApp
#     try:
#         response = llm_service.generate_response(message.message)
#         response = "".join([token async for token in response])
#     except Exception as e:
#         logger.error(f"Error al generar la respuesta del modelo: {str(e)}")
#         return JSONResponse(content={"error": "Error al generar respuesta"}, status_code=500)

#     reply = deepcopy(message)
#     reply.direction = "outbound"
#     reply.message = response
#     reply.mtype = "text"
#     reply.time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # Enviar mensaje usando Twilio
#     account_sid = os.getenv("TWILIO_ACCOUNT_SID")
#     auth_token = os.getenv("TWILIO_AUTH_TOKEN")
#     client = Client(account_sid, auth_token)

#     content = { "status": True, "message": "A response has been sent back to Sender via WhatsApp" }
#     try:
#         client.messages.create(
#             body=reply.message,
#             from_="whatsapp:"+toN,
#             to="whatsapp:"+reply.number
#         )
#     except Exception as e:
#         logger.error(f"Error al enviar mensaje con Twilio: {str(e)}")
#         content = { "status": False, "error": f"Cannot reply to WhatsApp message, possibly Access Denied: {str(e)}" }

#     # Guardar en base de datos
#     try:
#         db.Insert(message)  # Guardar el mensaje original
#         db.Insert(reply)    # Guardar el mensaje de respuesta
#         logger.debug(f"Mensajes almacenados: {message.message}, {reply.message}")
#     except Exception as e:
#         logger.error(f"Error al insertar en la base de datos: {str(e)}")
#         return JSONResponse(content={"error": "Error al guardar los mensajes en la base de datos"}, status_code=500)
    
#     return JSONResponse(content=content)




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