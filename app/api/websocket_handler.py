import base64
import audioop
import logging
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from starlette.websockets import WebSocketDisconnect


class WebSocketHandler:
    duration = 0.02

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_sid = None
        self.initial_data = None
        self.switch = None

    async def connect(self):
        await self.websocket.accept()
        async for _ in self.process_stream():
            if self.stream_sid:
                break

    async def process_stream(self):
        try:
            while True:
                data = await self.websocket.receive_json()
                chunk = await self.handle_event(data)
                if chunk:
                    yield chunk

        except WebSocketDisconnect:
            logging.getLogger("uvicorn").warning("WebSocket disconnected")
            raise WebSocketDisconnect

        except Exception as e:
            logging.getLogger("uvicorn").error(
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

        if rms > 450 and (self.switch == "listening" or self.switch is None):
            return raw_audio_data
        else:
            raw_audio_data = await self.generate_silence()
            return raw_audio_data

    async def generate_silence(self, sample_width=2, sample_rate=8000):
        num_samples = int(self.duration * sample_rate)
        silence_data = b"\x00" * (num_samples * sample_width)
        return audioop.lin2ulaw(silence_data, sample_width)

    async def send_audio(self, audio_data):
        if self.is_connected:
            await self.websocket.send_json(
                {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": audio_data},
                }
            )

    async def send_mark(self, mark):
        if self.is_connected:
            await self.websocket.send_json(
                {
                    "event": "mark",
                    "streamSid": self.stream_sid,
                    "mark": {"name": mark},
                }
            )

    @property
    def is_connected(self):
        return (
            self.websocket.application_state == WebSocketState.CONNECTED
            and self.websocket.client_state == WebSocketState.CONNECTED
        )
