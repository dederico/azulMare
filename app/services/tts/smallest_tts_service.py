from typing import AsyncGenerator, Literal
from app.services.tts.tts_service import TTSService
from smallest.tts import Smallest
from smallest.async_tts import AsyncSmallest
from smallest import TextToAudioStream
import base64
import logging

class SmallestTTSService(TTSService):
    def __init__(
        self,
        api_key: str,
        model: str = "lightning",
        voice_id: str = "Carlos",
        speed: float = 1.0,
        sample_rate: int = 8000,
        add_wav_header: bool = False,
        transliterate: bool = False,
        remove_extra_silence: bool = True,
        use_async: bool = True,
        stream_results: bool = False
    ):
        self.stream_results = stream_results
        self.api_key = api_key
        self.model = model
        self.voice_id = voice_id
        self.speed = speed
        self.sample_rate = sample_rate
        self.add_wav_header = add_wav_header
        self.transliterate = transliterate
        self.remove_extra_silence = remove_extra_silence

        if model == "lightning-multilingual":
            logging.info("Using Lightning Multilingual model (beta). This model supports 30 languages.")
        if use_async:
            self.tts_instance = AsyncSmallest(
                api_key=self.api_key,
                model=self.model,
                voice_id=self.voice_id,
                speed=self.speed,
                sample_rate=self.sample_rate,
                add_wav_header=self.add_wav_header,
                transliterate=self.transliterate,
                remove_extra_silence=self.remove_extra_silence
            )
        else:
            self.tts_instance = Smallest(
                api_key=self.api_key,
                model=self.model,
                voice_id=self.voice_id,
                speed=self.speed,
                sample_rate=self.sample_rate,
                add_wav_header=self.add_wav_header,
                transliterate=self.transliterate,
                remove_extra_silence=self.remove_extra_silence
            )

        self.stream_processor = TextToAudioStream(self.tts_instance)

    async def synthesize(self, text: str) -> str:
        if isinstance(self.tts_instance, AsyncSmallest):
            audio_content = await self.tts_instance.synthesize(text)
        else:
            audio_content = self.tts_instance.synthesize(text)
        return base64.b64encode(audio_content).decode('utf-8')

    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        async def text_generator():
            yield text

        async for audio_chunk in self.stream_processor.process(text_generator()):
            yield base64.b64encode(audio_chunk).decode('utf-8')