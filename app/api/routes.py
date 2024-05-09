import base64
import aiohttp
import logging
import urllib.parse
from fastapi import HTTPException, APIRouter, Request, Response, WebSocket
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.api.websocket_handler import WebSocketHandler
from app.core.orchestrator import Orchestrator
from app.services.stt.amazon_service import AmazonTranscribeService
from app.services.stt.deepgram_service import DeepgramService
from app.services.llm.openai_service import OpenAIService
from app.services.tts.eleven_service import ElevenTTSService
from app.services.tts.polly_service import AmazonTTSService
from app.services.functions.function_registry import registered_functions
from app.services.llm.config.system import system_message
from app.services.functions.function_manager import FunctionManager
from app.services.functions.implementations.identify import get_customer_identity

from twilio.rest import Client
from urllib.parse import parse_qs
import os
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()

try:

    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
    ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
    VOICE_ID = os.environ["VOICE_ID"]
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_REGION = os.environ["AWS_REGION"]
    TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
    TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
except Exception as env_exception:
    raise Exception("Missing environment variables") from env_exception

NGROK_URL = os.environ.get("HOSTNAME")

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


@router.post("/amd_detect")
async def amd_detect(request: Request):
    host = request.headers.get("host")
    # Ensure these are correctly fetching your Twilio credentials
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if not account_sid or not auth_token:
        raise HTTPException(status_code=500, detail="Twilio credentials are not set")

    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode()
        parsed_body = parse_qs(body_str)

        print(f"Received AMD callback data: {parsed_body}")

        answered_by = parsed_body.get("AnsweredBy", [None])[0]
        call_sid = parsed_body.get("CallSid", [None])[0]

        # Basic validation
        if not call_sid:
            print("Call SID missing from request")
            return {"detail": "Invalid request"}

        if answered_by is None:
            print(f"AMD result missing for call SID: {call_sid}")
            return {"detail": "AMD result missing"}

        # Log the AMD detection result
        print(f"Call {call_sid} answered by: {answered_by}")

        # If AMD detected an answering machine, you can hang up the call
        if answered_by.startswith("machine_start"):
            client = Client(account_sid, auth_token)
            try:
                call = client.calls(call_sid).update(status="completed")
                logging.getLogger("uvicorn").info(f"Call {call_sid} ended due to AMD detection: {answered_by}")
            except Exception as e:
                logging.getLogger("uvicorn").error(f"Error updating call status for {call_sid}: {str(e)}")
                return {"detail": "Failed to update call status"}

        # If answered by a human, redirect the call to /stream
        elif answered_by == "human":
            # Use the Redirect verb in TwiML to redirect the call
            response = VoiceResponse()
            response.redirect(NGROK_URL)
            return Response(content=str(response), media_type="application/xml")

        return {"detail": "Call handled successfully"}

    except Exception as e:
        print(f"Exception in /amd_detect: {e}")
        return {"detail": "Internal Server Error"}



@router.websocket("/stream")
async def websocket_endpoint(ws: WebSocket):
    websocket_handler = WebSocketHandler(ws)
    await websocket_handler.connect()

    #stt_service = DeepgramService(DEEPGRAM_API_KEY)

    # Set up Speech-to-Text (STT) service (e.g., Amazon Transcribe)
    stt_service = AmazonTranscribeService(
        region="us-east-1",
        sample_rate=8000,
        enhanced=False,
        language="en-US",
    )

    # Create a function manager to manage registered functions
    function_manager = FunctionManager(registered_functions)

    # Process the audio stream
    async for _ in websocket_handler.process_stream():
        break

    # Get the current date and time
    now = datetime.now()

    # Format the date as a string
    date_string = now.strftime("%Y-%m-%d")

    # Get call SID and customer identity
    call_sid = websocket_handler.call_sid
    customer_identity = await get_customer_identity(call_sid)

    # Set up Language Model (LM) service (e.g., OpenAI)
    llm_service = OpenAIService(
        api_key=OPENAI_API_KEY,
        system=system_message.format(customer_name=customer_identity, call_sid=call_sid, date=date_string, now=now),
        function_manager=function_manager,
        model="gpt-4-1106-preview",
        # model="gpt-3.5-turbo-1106",
    )

    # Set up Text-to-Speech (TTS) service (e.g., Amazon Polly)
    tts_service = AmazonTTSService(
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        stream_results=False,
    )

        # tts_service = ElevenTTSService(
    #     api_key=ELEVENLABS_API_KEY,
    #     voice_id=VOICE_ID,
    #     similarity_boost=0.6,
    #     stability=0.7,
    #     stream_results=True,
    # )

    # Set up the orchestrator
    orchestrator = Orchestrator(
        websocket_handler=websocket_handler,
        stt_service=stt_service,
        llm_service=llm_service,
        tts_service=tts_service,
    )

    try:
        # Process the audio stream using the orchestrator
        await orchestrator.process_audio_stream()
    except Exception as orch_exception:
        await stt_service.finish_transcription()
        logging.getLogger("uvicorn").warning(f"Call ended with exception: {orch_exception}")

    # Log that the connection is closed
    logging.getLogger("uvicorn").info("Connection closed")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/make_call")
async def make_call(request: Request):
    account_sid = TWILIO_ACCOUNT_SID
    auth_token = TWILIO_AUTH_TOKEN
    host = NGROK_URL
    number = os.getenv("NUMBER")

    # Ensure Twilio credentials are set
    if not account_sid or not auth_token:
        return {"detail": "Twilio credentials are not set"}

    credentials = f"{account_sid}:{auth_token}"
    token = base64.b64encode(credentials.encode()).decode()

    # Set up parameters for making the call
    payload_params = {
        "MachineDetection": "Enable",
        "MachineDetectionTimeout": "03",
        "Timeout": "07",
        "AsyncAmd": "true",
        "Url": f"{host}/",
        "AsyncAmdStatusCallback": f"{host}/amd_detect",
        "To": "+525541634143",  # Update with the desired recipient number
        "From": number,
    }

    # Encode payload parameters
    payload = urllib.parse.urlencode(payload_params)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

    # Set up headers for the HTTP request
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {token}",
    }

    try:
        # Make the Twilio API call to initiate the phone call
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as response:
                response.raise_for_status()
                r = await response.text()
                logging.getLogger("uvicorn").info(r)
                return {"detail": "Call initiated successfully"}
    except Exception as e:
        logging.getLogger("uvicorn").warning(f"Call failed with error: {e}")
        return {"detail": f"Call failed with error: {e}"}
    
@router.post("/handle_redirected_call")
async def handle_redirected_call(request: Request):
# Create a new VoiceResponse
    response = VoiceResponse()
# Add a Say verb to the response to say a message
    response.say("This is a redirect call.", voice='Polly.Salli', language='en-US')
# Convert the VoiceResponse to XML
    text = response.to_xml()
# Return the XML as a response with the correct media type
    return Response(content=text, media_type="text/xml")