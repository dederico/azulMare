import base64
import audioop
from fastapi import WebSocket
from app.util.logger import logger
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect

class WebSocketHandler:
    duration = 0.02

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid = None
        self.initial_data = None
        self.switch = None
        self.playsequence = []

    async def connect(self):
        await self.websocket.accept()

        logger.debug("Customer call connected processing audio channel")
        async for _ in self.process_stream():
            if self.stream_sid:
                break

    async def process_stream(self):
        try:
            while True:
                #logger.debug("Waiting for customer Audio_Message")
                data = await self.websocket.receive_json()

                #logger.debug("Received customer audio, processing chunk")
                chunk = await self.handle_event(data)
                if chunk:
                    yield chunk

        except WebSocketDisconnect:
            logger.warning("WebSocket disconnected reason unknown")
            raise WebSocketDisconnect

        except Exception as e:
            logger.error(
                f"Error in WebSocket stream processing: {e}"
            )
            raise e

    async def handle_event(self, data):
        if data["event"] == "start":
            self.initial_data = data["start"]
            self.stream_sid = data["streamSid"]
            self.call_sid = data["start"]["callSid"]

        elif data["event"] == "media":
            return await self.process_media_event(data)

        elif data["event"] == "mark":
            self.switch = data["mark"]["name"]

    async def process_media_event(self, data):
        audio_payload = data["media"]["payload"]
        audio_content = base64.b64decode(audio_payload)
        raw_audio_data = audioop.ulaw2lin(audio_content, 2)
        rms = audioop.rms(raw_audio_data, 2)

        if rms > 300 and (self.switch == "listening" or self.switch is None):
            self.playsequence.append(audio_payload)
            return raw_audio_data
        else:
            raw_audio_data = await self.generate_silence()
            return raw_audio_data

    async def generate_silence(self, sample_width=2, sample_rate=8000):
        # logger.debug("Generating and forwarding silence frame")
        num_samples = int(self.duration * sample_rate)
        silence_data = b"\x00" * (num_samples * sample_width)
        return audioop.lin2ulaw(silence_data, sample_width)

    async def send_audio(self, audio_data):
        logger.debug("Received audio frame from Robot")
        if self.is_connected:
            logger.debug("Socket is connected, sending audio frame to customer")
            self.playsequence.append(audio_data)
            await self.websocket.send_json(
                {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": audio_data},
                }
            )
        else:
            logger.debug("User is not connected anymore skipping audio sending to customer")

    async def send_mark(self, mark):
        logger.debug("Sending {} mark to Twilio".format(mark))
        if self.is_connected:
            await self.websocket.send_json(
                {
                    "event": "mark",
                    "streamSid": self.stream_sid,
                    "mark": {"name": mark},
                }
            )
        else:
            logger.debug("Socket not connected hence mark Not_Sent")

    @property
    def is_connected(self):
        return (
            self.websocket.application_state == WebSocketState.CONNECTED
            and self.websocket.client_state == WebSocketState.CONNECTED
        )
    
    @property
    def audio_sequence(self):
        return self.playsequence