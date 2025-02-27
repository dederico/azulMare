import logging
import time
import asyncio
from collections import deque
from .stt_service import STTService
from deepgram import Deepgram
from pydub import AudioSegment
import io

class DeepgramService(STTService):
    def __init__(self, api_key, target_chunk_size=4000):  # 🔥 Ajustamos a 3200 bytes (~200 ms)
        self.deepgram = Deepgram(api_key)
        self.deepgramLive = None
        self.transcript_received_callback = None
        self.timestamps = deque() 
        self.chunk_counter = 0
        self.max_timestamps = 100
        self.target_chunk_size = target_chunk_size  # 🔥 Tamaño del chunk acumulado
        self.audio_buffer = b""  # 🔥 Buffer de audio antes de enviarlo
    async def transcribe(self, chunk):
        """Acumula chunks en un buffer antes de enviarlos a Deepgram."""
        if self.deepgramLive:
            self.audio_buffer += chunk  # 🔥 Acumula los datos en un buffer

            # 🔥 Solo enviamos si el buffer es suficientemente grande
            if len(self.audio_buffer) >= self.target_chunk_size:
                # chunk_size = len(self.audio_buffer)
                # duration_ms = (chunk_size / (8000 * 2)) * 1000  # 🔥 Estima duración en ms
                
                # logging.getLogger("uvicorn").info(
                #     f"Enviando chunk de {chunk_size} bytes (~{duration_ms:.2f} ms)"
                # )
 
                # timestamp = time.time()
                # self.timestamps.append(timestamp)

                # # 🔥 Evita acumulación excesiva de timestamps
                # if len(self.timestamps) > self.max_timestamps:
                #     self.timestamps.popleft()

                self.deepgramLive.send(self.audio_buffer)  # 🔥 Envía el buffer acumulado
                self.audio_buffer = b""  # 🔥 Limpia el buffer después de enviarlo

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
                ),
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
            return dBFS < silence_threshold  # Si es menor, lo consideramos silencio
        except Exception as e:
            logging.getLogger("uvicorn").error(f"Error al analizar chunk: {e}")
            return True
    async def set_transcript_received_callback(self, callback):
        """Procesa la transcripción y mide latencia con `deque` para evitar acumulación incorrecta."""
        if self.deepgramLive:
            async def wrapper(response):
                # received_time = time.time()

                # if self.timestamps:
                #     sent_time = self.timestamps.popleft()  # 🔥 FIFO, el más antiguo primero
                #     latency_ms = (received_time - sent_time) * 1000  # Convierte a ms

                #     logging.getLogger("uvicorn").warning(f"Latencia de transcripción: {latency_ms:.2f} ms")
                # else:
                #     logging.getLogger("uvicorn").warning("No hay timestamps disponibles.")

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
