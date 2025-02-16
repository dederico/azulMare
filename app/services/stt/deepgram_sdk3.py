import logging
from .stt_service import STTService
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

logger = logging.getLogger(__name__)

class DeepgramService(STTService):
    def __init__(self, api_key):
        self.deepgram = DeepgramClient(api_key)
        self.dg_connection = None
        self.transcript_received_callback = None

    async def start_transcription(self, language="es", sample_rate=8000):
        try:
            self.dg_connection = self.deepgram.listen.websocket.v("1")
            
            # Define callback for transcription messages
            async def on_message(self, result, **kwargs):
                if self.transcript_received_callback:
                    await self.transcript_received_callback(result)

            self.dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

            # Connect to websocket
            options = LiveOptions(
                model="general",
                language=language,
                encoding="linear16",
                channels=1,
                sample_rate=sample_rate,
                smart_format=True,
                interim_results=False,
            )
            await self.dg_connection.start(options)
            
            logger.info("Successfully connected to Deepgram and started transcription.")
        except Exception as e:
            logger.error(f"Could not open socket: {e}")
            raise

    async def transcribe(self, chunk):
        if self.dg_connection:
            try:
                await self.dg_connection.send(chunk)
            except Exception as e:
                logger.error(f"Error sending chunk to Deepgram: {e}")
                # You might want to implement reconnection logic here

    async def set_transcript_received_callback(self, callback):
        self.transcript_received_callback = callback

    async def finish_transcription(self):
        if self.dg_connection:
            try:
                await self.dg_connection.finish()
                logger.info("Deepgram transcription finished successfully.")
            except Exception as e:
                logger.error(f"Error finishing Deepgram transcription: {e}")