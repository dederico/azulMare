import base64
import aiohttp
from deepgram import DeepgramClient, SpeakOptions
from app.services.tts.tts_service import TTSService

class DeepgramTTSService(TTSService):
    def __init__(
        self,
        api_key: str | None,
        voice: str = "aura-asteria-en",
        logger = False
    ):
        self.api_key = api_key
        self.voice = voice
        self.logger = logger or print
        self.deepgram = DeepgramClient(api_key)

    async def synthesize(self, text: str):
        self.logger("Preparing Sync TTS request for text " + text)
        url = "https://api.deepgram.com/v1/speak"

        payload = {
            "text": text,
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        options = SpeakOptions(
            model=self.voice,
        )

        self.logger("Initializing TTS request session")
        async with aiohttp.ClientSession() as session:
            self.logger("Session ready making request")
            async with session.post(
                url, json=payload, headers=headers, params=options.to_dict()
            ) as response:
                if response.status == 200:
                    self.logger("Got a valid response of 200")
                    audio_data = await response.read()

                    self.logger("Decoding B64 to valid audio chunk")
                    base64_audio = base64.b64encode(audio_data).decode()
                    return base64_audio
                else:
                    self.logger(f"Received an invalid response of {response.status}")

    async def stream_synthesize(self, text: str):
        self.logger("Initiating stream based TTS request for text " + text)
        url = "https://api.deepgram.com/v1/speak"

        payload = {
            "text": text,
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        options = SpeakOptions(
            model=self.voice,
            streaming=True
        )

        self.logger("Initializing a TTS session for request")
        async with aiohttp.ClientSession() as session:
            self.logger("Session established successfully, making request")
            async with session.post(
                url, json=payload, headers=headers, params=options.to_dict()
            ) as response:
                response.raise_for_status()
                if response.status == 200:
                    self.logger("Received valid response of 200")
                    async for chunk in response.content.iter_any():
                        self.logger("Decoding audio B64 chunk to valid audio frame")
                        base64_chunk = base64.b64encode(chunk).decode()
                        yield base64_chunk
                else:
                    self.logger(f"Received invalid response with status code {response.status}")