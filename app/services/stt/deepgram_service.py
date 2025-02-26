import logging
from .stt_service import STTService
from deepgram import Deepgram


class DeepgramService(STTService):
    def __init__(self, api_key):
        self.deepgram = Deepgram(api_key)
        self.deepgramLive = None
        self.transcript_received_callback = None

    async def start_transcription(self, language="es", sample_rate=8000):
        try:
            self.deepgramLive = await self.deepgram.transcription.live(
                {
                    "smart_format": True,
                    "interim_results": False,
                    "language": language,
                    "encoding": "linear16",
                    "model": "2-general",
                    "tier": "nova",
                    "sample_rate": sample_rate,
                    "keepAlive": True,
                }
            )
            self.deepgramLive.register_handler(
                self.deepgramLive.event.CLOSE,  # type: ignore
                lambda c: logging.getLogger("uvicorn").warning(
                    f"Deepgram connection closed with code {c}."
                ),
            )

        except Exception as e:
            logging.getLogger("uvicorn").error(f"Could not open socket: {e}")

    async def transcribe(self, chunk):
        if self.deepgramLive:
            self.deepgramLive.send(chunk)

    async def set_transcript_received_callback(self, callback):
        if self.deepgramLive:
            self.deepgramLive.register_handler(
                self.deepgramLive.event.TRANSCRIPT_RECEIVED, callback  # type: ignore
            )

    async def finish_transcription(self):
        if self.deepgramLive:
            await self.deepgramLive.finish()