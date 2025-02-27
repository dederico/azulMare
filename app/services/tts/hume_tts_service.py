from typing import AsyncGenerator, List
from app.services.tts.tts_service import TTSService
from hume import HumeClient
from hume.tts import FormatMp3, PostedContextWithUtterances, PostedUtterance
import base64
import logging
import aiohttp
import asyncio

class HumeTTSService(TTSService):
    def __init__(
        self,
        api_key: str,
        format: str = "mp3",
        num_generations: int = 1,
        logger=None
    ):
        self.api_key = api_key
        self.format = format
        self.num_generations = num_generations
        self.logger = logger or logging.getLogger(__name__)
        self.client = HumeClient(api_key=self.api_key)

    async def synthesize(self, text: str, description: str = "") -> str:
        try:
            response = await self._synthesize_internal(text, description)
            audio_content = response[0].audio  # Assuming the first generation is used
            return base64.b64encode(audio_content).decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error in Hume TTS synthesis: {str(e)}")
            raise

    async def stream_synthesize(self, text: str, description: str = "") -> AsyncGenerator[str, None]:
        try:
            response = await self._synthesize_internal(text, description)
            audio_content = response[0].audio  # Assuming the first generation is used
            
            # Simulating streaming by chunking the audio content
            chunk_size = 1024  # Adjust as needed
            for i in range(0, len(audio_content), chunk_size):
                chunk = audio_content[i:i+chunk_size]
                yield base64.b64encode(chunk).decode('utf-8')
                await asyncio.sleep(0.1)  # Simulate streaming delay
        except Exception as e:
            self.logger.error(f"Error in Hume TTS stream synthesis: {str(e)}")
            raise

    async def _synthesize_internal(self, text: str, description: str = ""):
        utterances = [
            PostedUtterance(
                text=text,
                description=description or "Default voice description"
            )
        ]

        context = PostedContextWithUtterances(utterances=[])

        format_class = FormatMp3 if self.format.lower() == "mp3" else FormatMp3  # Add more formats if needed

        return await self.client.tts.synthesize_json(
            utterances=utterances,
            context=context,
            format=format_class(),
            num_generations=self.num_generations
        )

    async def set_voice(self, voice_id: str):
        # Hume doesn't have a direct voice_id setting, so we'll use this method to update the description
        self.default_description = voice_id

    async def list_voices(self) -> List[dict]:
        # Hume doesn't provide a list of predefined voices, so we'll return an empty list or implement custom logic
        return []