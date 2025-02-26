import asyncio
import json
import base64
import websockets
from typing import AsyncGenerator
from app.services.tts.tts_service import TTSService


class RimeTTSService(TTSService):
    def __init__(
        self,
        api_key: str = "Y4TqiR1WypvkKdZp3D89soMnnkNBLYwboX81y-z4E9Y",
        speaker: str = "Isa",
        model_id: str = "mistv2",
        audio_format: str = "pcm",
        language: str = "spa",
        stream_results: bool = True,
        logger=None
    ):
        self.api_key = api_key
        self.speaker = speaker
        self.model_id = model_id
        self.audio_format = audio_format
        self.language = language
        self.stream_results = stream_results
        self.logger = logger or print
        self.url = f"wss://users-ws.rime.ai/ws2?speaker={self.speaker}&modelId={self.model_id}&audioFormat={self.audio_format}"
        self.auth_headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

    async def synthesize(self, text: str) -> str:
        self.logger(f"Preparing TTS request for text: {text}")
        audio_data = await self._run_synthesis([{"text": text}, {"operation": "eos"}])
        return base64.b64encode(audio_data).decode()

    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        self.logger(f"Initiating stream based TTS request for text: {text}")
        async for chunk in self._stream_synthesis([{"text": text}, {"operation": "eos"}]):
            yield chunk

    async def _run_synthesis(self, messages):
        audio_data = b''
        async with websockets.connect(self.url, extra_headers=self.auth_headers) as websocket:
            send_task = asyncio.create_task(self._send_messages(websocket, messages))
            async for chunk in self._handle_audio(websocket):
                audio_data += base64.b64decode(chunk)
            await send_task
        return audio_data

    async def _stream_synthesis(self, messages):
        async with websockets.connect(self.url, extra_headers=self.auth_headers) as websocket:
            send_task = asyncio.create_task(self._send_messages(websocket, messages))
            async for chunk in self._handle_audio(websocket):
                yield chunk
            await send_task

    async def _send_messages(self, websocket, messages):
        for message in messages:
            await websocket.send(json.dumps(message))

    async def _handle_audio(self, websocket):
        while True:
            try:
                audio = await websocket.recv()
            except websockets.exceptions.ConnectionClosedOK:
                break
            message = json.loads(audio)
            self.logger(f"Received message: {message}")
            if message['type'] == 'chunk':
                yield message['data']  # This is already base64 encoded