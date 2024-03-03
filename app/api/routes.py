import base64
import aiohttp
import logging
import urllib.parse
import os

from dotenv import load_dotenv

load_dotenv()
from fastapi import APIRouter, Request, Response, WebSocket
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.api.websocket_handler import WebSocketHandler
from app.core.orchestrator import Orchestrator
from app.services.stt.deepgram_service import DeepgramService
from app.services.llm.openai_service import OpenAIService
from app.services.tts.eleven_service import ElevenTTSService
from app.services.tts.polly_service import AmazonTTSService
from app.services.functions.function_registry import registered_functions
from app.services.llm.config.system import system_message
from app.services.functions.function_manager import FunctionManager
from twilio.rest import Client
from urllib.parse import parse_qs


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
    print(text)
    return Response(content=text, media_type="text/xml")


@router.websocket("/stream")
async def websocket_endpoint(ws: WebSocket):
    websocket_handler = WebSocketHandler(ws)
    await websocket_handler.connect()

    stt_service = DeepgramService(DEEPGRAM_API_KEY)

    function_manager = FunctionManager(registered_functions)

    llm_service = OpenAIService(
        api_key=OPENAI_API_KEY,
        system=system_message,
        function_manager=function_manager,
        model="gpt-4-1106-preview",
        # model="gpt-3.5-turbo-1106",
    )

    # tts_service = ElevenTTSService(
    #     api_key=ELEVENLABS_API_KEY,
    #     voice_id=VOICE_ID,
    #     similarity_boost=0.6,
    #     stability=0.7,
    #     stream_results=True,
    # )

    tts_service = AmazonTTSService(
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        stream_results=False,
    )

    orchestrator = Orchestrator(
        websocket_handler=websocket_handler,
        stt_service=stt_service,
        llm_service=llm_service,
        tts_service=tts_service,
    )
    try:
        await orchestrator.process_audio_stream()
    except:
        await stt_service.finish_transcription()
        logging.getLogger("uvicorn").warning("Call ended")


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

        logging.getLogger("uvicorn").warning(
            f"Machine - {answered_by} detected for: {call_sid}"
        )


@router.get("/health")
async def health():
    return {"status": "ok"}


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
                logging.getLogger("uvicorn").info(r)
            except Exception as e:
                logging.getLogger("uvicorn").warning(f"Call failed with error: {e}")