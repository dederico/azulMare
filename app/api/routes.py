import base64
import aiohttp
import logging
import urllib.parse
import os
import json
from io import StringIO
from dotenv import load_dotenv

load_dotenv()
from fastapi import APIRouter, Request, Response, WebSocket
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
from app.util.logger import logger, get_thread_log_handler, cleanup_call_logger
from app.models.Call import Call
from app.models.Config import Config
from app.util.factory import Hooks
from app.util.database import LocalStorage
from app.services.functions.implementations.identify import get_customer_identity
from app.services.functions.implementations.date import get_current_date

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")

router = APIRouter()

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
    logHandler = get_thread_log_handler()

    logger.info("Got new INCOMING_CALL")
    db = LocalStorage()
    config = { conf.name: conf.value for conf in db.GetAll(Config) }

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
        language="es-US"
        #language=config["language"]
    )

    function_manager = FunctionManager(registered_functions)

    # Get the current date and time
    now = datetime.now()
    call = db.Search(Call(callUid = websocket_handler.call_sid), True)
    if call:
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

    # Format the date as a string
    date_string = now.strftime("%Y-%m-%d")

    current_date = await get_current_date()

    # Get call SID and customer identity
    call_sid = websocket_handler.call_sid
    customer_identity = await get_customer_identity(call_sid)
    call.callerName = customer_identity

    logger.debug("Initializing LLM service for the new call")
    llm_service = OpenAIService(
        api_key=OPENAI_API_KEY,
        system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date2=date_string, now=now, date=current_date),
        function_manager=function_manager,
        model=config.get("model") or "gpt-3.5-turbo-1106"
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
        language="es-US"
        #language=config["language"]
    )

    logger.debug("Initializing orchestrator for the call")
    orchestrator = Orchestrator(
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
    call.callScript = json.dumps(stats['Script'])
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