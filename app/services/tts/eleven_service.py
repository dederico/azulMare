import base64
import time
import aiohttp
from app.services.tts.tts_service import TTSService


class ElevenTTSService(TTSService):
    def __init__(
        self,
        api_key: str | None,
        voice_id: str = "xZQN7wZ4rvyoqsqAzqtB",
        similarity_boost: float = 0.6,
        stability: float = 0.4,
        stream_results: bool = False,
        logger = False
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.similarity_boost = similarity_boost
        self.stability = stability
        self.stream_results = stream_results
        self.logger = logger or print

    async def synthesize(self, text: str):
        self.logger("Preparing Sync TTS request for text " + text)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        querystring = {"optimize_streaming_latency": "3", "output_format": "ulaw_8000"}

        payload = {
            "model_id": "eleven_multilingual_v1",
            "text": text,
            "voice_settings": {
                "similarity_boost": 0.6,
                "stability": 0.6,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": "be6ba447f38b2f84255363d41d5fe297",
            "Content-Type": "application/json",
        }

        self.logger("Initializing TTS request session")
        async with aiohttp.ClientSession() as session:
            self.logger("Session ready making request")
            async with session.post(
                url, json=payload, headers=headers, params=querystring
            ) as response:
                if response.status == 200:
                    self.logger("Got a valid response of 200")
                    audio_data = await response.read()

                    self.logger("Decoding B64 to valid audio chunk")
                    base64_audio = base64.b64encode(audio_data).decode()
                    return base64_audio
                else:
                    self.logger("Received a invalid response of " + response.status)

    async def stream_synthesize(self, text: str):
        self.logger("Initiating stream based TTS request for text " + text)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        querystring = {"optimize_streaming_latency": "3", "output_format": "ulaw_8000"}

        payload = {
            "model_id": "eleven_multilingual_v1",
            "text": text,
            "voice_settings": {
                "similarity_boost": self.similarity_boost,
                "stability": self.stability,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        # start = time.perf_counter()
        self.logger("Initializing a TTS session for request")
        async with aiohttp.ClientSession() as session:
            self.logger("Session established successfully, making request")
            async with session.post(
                url, json=payload, headers=headers, params=querystring
            ) as response:
                response.raise_for_status()
                if response.status == 200:
                    self.logger("Received valid response of 200")
                    async for chunk in response.content.iter_any():
                        # print(time.perf_counter() - start)
                        self.logger("Decoding audio B64 chunk to valid audio frame")
                        base64_chunk = base64.b64encode(chunk).decode()
                        yield base64_chunk
                else:
                    self.logger("Received invalid response with status code " + response.status)