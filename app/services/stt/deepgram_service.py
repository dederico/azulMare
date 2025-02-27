import logging
import time
import asyncio
from collections import OrderedDict  # 👈 Importamos OrderedDict
from .stt_service import STTService
from deepgram import Deepgram


class DeepgramService(STTService):
    def __init__(self, api_key):
        self.deepgram = Deepgram(api_key)
        self.deepgramLive = None
        self.transcript_received_callback = None
        self.timestamps = OrderedDict()  # 👈 Usamos OrderedDict para mantener el orden de los chunks
        self.chunk_counter = 0  # Contador de fragmentos enviados

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
        """Envía audio a Deepgram y registra el tiempo de envío usando un contador."""
        if self.deepgramLive:
            timestamp = time.time()  # Guardar tiempo de envío
            chunk_id = self.chunk_counter  # Usamos un contador único por chunk
            self.timestamps[chunk_id] = timestamp  # Guardamos el tiempo de envío
            self.chunk_counter += 1  # Incrementamos el contador para el siguiente chunk
            self.deepgramLive.send(chunk)

    async def set_transcript_received_callback(self, callback):
        """Registra un callback para procesar la transcripción y medir la latencia."""
        if self.deepgramLive:
            async def wrapper(response):
                received_time = time.time()  # Tiempo de recepción
                # Buscar el chunk_id más antiguo para calcular la latencia
                if self.timestamps:
                    chunk_id, sent_time = self.timestamps.popitem(last=False)  # Obtener el primer chunk enviado
                    latency_ms = (received_time - sent_time) * 1000  # Convertir a milisegundos
                    logging.getLogger("uvicorn").warning(f"Latencia de transcripción para chunk {chunk_id}: {latency_ms:.2f} ms")
                else:
                    logging.getLogger("uvicorn").warning("No hay chunks en timestamps para calcular latencia")

                # Verifica si callback es una corutina y usa await si es necesario
                if asyncio.iscoroutinefunction(callback):
                    await callback(response)
                else:
                    callback(response)

            self.deepgramLive.register_handler(
                self.deepgramLive.event.TRANSCRIPT_RECEIVED, wrapper  # type: ignore
            )

    async def finish_transcription(self):
        """Cierra la conexión con Deepgram."""
        if self.deepgramLive:
            await self.deepgramLive.finish()
