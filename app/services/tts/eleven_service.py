import base64
import time
import aiohttp
from app.services.tts.tts_service import TTSService


class ElevenTTSService(TTSService):
    def __init__(
        self,
        api_key: str | None,
        voice_id: str = "AeHJuJE0pvOWBfJBXGkj",
        similarity_boost: float = 0.6,
        stability: float = 0.4,
        stream_results: bool = False,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.similarity_boost = similarity_boost
        self.stability = stability
        self.stream_results = stream_results

    async def synthesize(self, text: str):
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

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, params=querystring
            ) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    base64_audio = base64.b64encode(audio_data).decode()
                    return base64_audio

    async def stream_synthesize(self, text: str):
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
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, params=querystring
            ) as response:
                response.raise_for_status()
                if response.status == 200:
                    async for chunk in response.content.iter_any():
                        # print(time.perf_counter() - start)
                        base64_chunk = base64.b64encode(chunk).decode()
                        yield base64_chunk