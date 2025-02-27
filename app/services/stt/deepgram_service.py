import logging
import time
import asyncio
from collections import deque
from .stt_service import STTService
from deepgram import Deepgram
from pydub import AudioSegment
import io

class DeepgramService(STTService):
    def __init__(self, api_key):
        self.deepgram = Deepgram(api_key)
        self.deepgramLive = None
        self.transcript_received_callback = None
        self.timestamps = deque()  # 🔥 Usamos `deque` para manejar orden FIFO
        self.chunk_counter = 0
        self.max_timestamps = 100  # 🔥 Evita overflow de memoria

    async def start_transcription(self, language="es", sample_rate=8000):
        """Inicia la conexión a Deepgram."""
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
                self.deepgramLive.event.CLOSE,
                lambda c: logging.getLogger("uvicorn").warning(
                    f"Deepgram connection closed with code {c}. Reconnecting..."
                ) or asyncio.create_task(self.reconnect()),
            )

        except Exception as e:
            logging.getLogger("uvicorn").error(f"Could not open socket: {e}")

    async def reconnect(self):
        """Reintenta conectar a Deepgram en caso de desconexión."""
        await asyncio.sleep(2)
        logging.getLogger("uvicorn").info("Reconnecting to Deepgram...")
        await self.start_transcription()
    def is_silent(self, chunk, silence_threshold=-50):  # 🔥 Ajuste óptimo basado en logs
        """Verifica si un chunk de audio es silencio basado en dBFS."""
        if not isinstance(chunk, bytes):
            logging.getLogger("uvicorn").error("Error: Chunk inválido, se esperaba bytes.")
            return True

        try: 
            audio = AudioSegment.from_raw(io.BytesIO(chunk), sample_width=2, frame_rate=8000, channels=1)
            dBFS = audio.dBFS  # Obtiene el nivel de volumen del chunk 

            logging.getLogger("uvicorn").warning(f"🎤 Nivel de audio: {dBFS:.2f} dBFS (Umbral: {silence_threshold})")
 
            return dBFS < silence_threshold  # Si es menor, lo consideramos silencio
        except Exception as e:
            logging.getLogger("uvicorn").error(f"Error al analizar chunk: {e}")
            return True
    async def transcribe(self, chunk):
        """Envía audio a Deepgram y almacena el tiempo de envío en una cola."""
        if self.deepgramLive:
            # if not self.is_silent(chunk):
            timestamp = time.time()
            self.timestamps.append(timestamp)  # 🔥 Guarda solo timestamps, no IDs

            # 🔥 Elimina registros viejos si la cola excede el límite
            if len(self.timestamps) > self.max_timestamps:
                self.timestamps.popleft()
            self.deepgramLive.send(chunk)

    async def set_transcript_received_callback(self, callback):
        """Procesa la transcripción y mide latencia con `deque` para evitar acumulación incorrecta."""
        if self.deepgramLive:
            async def wrapper(response):
                received_time = time.time()

                if self.timestamps:
                    sent_time = self.timestamps.popleft()  # 🔥 FIFO, el más antiguo primero
                    latency_ms = (received_time - sent_time) * 1000  # Convierte a ms

                    logging.getLogger("uvicorn").warning(f"Latencia de transcripción: {latency_ms:.2f} ms")
                else:
                    logging.getLogger("uvicorn").warning("No hay timestamps disponibles.")

                # Si el callback es async, usa await
                if asyncio.iscoroutinefunction(callback):
                    await callback(response)
                else:
                    callback(response)

            self.deepgramLive.register_handler(
                self.deepgramLive.event.TRANSCRIPT_RECEIVED, wrapper
            )

    async def finish_transcription(self):
        """Cierra la conexión con Deepgram."""
        if self.deepgramLive:
            await self.deepgramLive.finish()
            logging.getLogger("uvicorn").info("Deepgram transcription finished.")
