import re
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

from app.util.logger import logger
from app.services.stt.stt_service import STTService
from app.services.llm.llm_service import LLMService
from app.services.tts.tts_service import TTSService
from app.api.websocket_handler import WebSocketHandler
from app.util.database import LocalStorage
from app.models.Config import Config

# Configurar la zona horaria de México
MEXICO_TZ = ZoneInfo("America/Mexico_City")

class Orchestrator:
    _instances = {}

    def __init__(
        self,
        call_sid,
        config,
        websocket_handler: WebSocketHandler,
        stt_service: STTService,
        llm_service: LLMService,
        tts_service: TTSService,
    ):
        self.config = config
        self.stats = { "Logs": [], "Script": [], "Status": "COMPLETED" }
        self.stt_service = stt_service
        self.llm_service = llm_service
        self.tts_service = tts_service
        self.websocket_handler = websocket_handler
        self.call_sid = call_sid  # Se usa para identificar cada instancia
        self._instances[call_sid] = self  # Guardar la instancia en el diccionario

        self.log(f"Orchestrator for call {call_sid} has been initialized")

    def log(self, msg):
        logger.debug(msg)
        self.stats["Logs"].append(msg)

    def logScript(self, msg):
        self.stats["Logs"].append(msg)
        timestamp = datetime.now(MEXICO_TZ).strftime("[%Y-%m-%d %H:%M:%S]")  # ✅ Zona horaria de México
        self.stats["Script"].append({ "role": "BOT", "dialog": f"{timestamp} - {msg}" })

    @classmethod
    def get_instance(cls, call_sid):
        """ Devuelve la instancia asociada a un `call_sid`, si existe """
        return cls._instances.get(call_sid)
    
    @classmethod
    def staticlog(cls, call_sid, msg):
        """ Llama a `log` en la instancia correcta según `call_sid` """
        instance = cls.get_instance(call_sid)
        if instance:
            instance.logScript(msg)
        else:
            logger.warning(f"No instance found for call_id {call_sid}")

    async def process_audio_stream(self):
        try:
            self.log("Greeting the caller")
            await self.greet()

            await self.stt_service.start_transcription()
            await self.stt_service.set_transcript_received_callback(self.handler)

            async for audio_chunk in self.websocket_handler.process_stream():
                try:
                    await self.stt_service.transcribe(audio_chunk)
                except Exception as e:
                    self.log(f"Error al enviar evento de audio a Transcribe: {e}")
                
            await self.stt_service.finish_transcription()
            self.log("Call ended Gracefully")
        except Exception as e:
            self.log(str(e))
            self.stats["Status"] = "PARTIAL_COMPLETED"

        logger.warning(self.stats)
        return self.stats

    async def handler(self, transcription: dict) -> None:
        if self.websocket_handler.is_connected and transcription.get("channel"):
            
            full_transcript = transcription["channel"]["alternatives"][0]["transcript"]
            
            if full_transcript:
                timestamp = datetime.now(MEXICO_TZ).strftime("[%Y-%m-%d %H:%M:%S]")  # ✅ Zona horaria de México
                self.stats["Script"].append({ "role": "CUSTOMER", "dialog":  f"{timestamp} - {full_transcript}" })
                logger.warning(f"CUSTOMER: {timestamp} - {full_transcript}")
                
                # Obtener la transcripción actual del cliente en LocalStorage
                current_customer_transcription = LocalStorage.get("transcription_for_analysis_customer", "")
                # Concatenar la nueva transcripción con la existente
                updated_customer_transcription = f"{current_customer_transcription} {full_transcript}".strip()
                # Guardar la transcripción actualizada en LocalStorage
                LocalStorage.set("transcription_for_analysis_customer", updated_customer_transcription)

                await self.websocket_handler.send_mark("not_listening")
                await self.process_transcript(full_transcript)
                await self.websocket_handler.send_mark("listening")

    async def process_transcript(self, transcript: str) -> None:
        buffer = ""

        self.log("Generating response from LLM service")
        generator = self.llm_service.generate_response(transcript)

        async for token in generator:  # type:ignore
            if not self.websocket_handler.is_connected:
                buffer = ""
                break
            buffer += token
            buffer = await self.process_buffer(buffer)

        if buffer:
            self.log("Invoking TTS engine on LLM response")
            await self.synthesize_and_send(buffer)

    async def process_buffer(self, buffer: str) -> str:
        sentence, remainder = self.contains_punctuation(buffer)
        if sentence and remainder:
            await self.synthesize_and_send(sentence)
            return remainder
        return buffer

    async def synthesize_and_send(self, text: str) -> None:
        timestamp = datetime.now(MEXICO_TZ).strftime("[%Y-%m-%d %H:%M:%S]")  # ✅ Zona horaria de México
        logger.warning(f"Speaking: {text}")
        self.stats["Script"].append({ "role": "BOT", "dialog": f"{timestamp} - {text}" })

        # Obtener el valor existente en LocalStorage
        current_bot_transcription = LocalStorage.get("transcription_for_analysis_bot", "")
        # Concatenar el nuevo texto al LocalStorage
        updated_bot_transcription = f"{current_bot_transcription} {text}".strip()
        # Guardar la transcripción actualizada
        LocalStorage.set("transcription_for_analysis_bot", updated_bot_transcription)
        
        if self.tts_service.stream_results:
            generator = self.tts_service.stream_synthesize(text)
            async for encoded_audio in generator:  # type:ignore
                await self.websocket_handler.send_audio(encoded_audio)
        else:
            encoded_audio = await self.tts_service.synthesize(text)
            await self.websocket_handler.send_audio(encoded_audio)

    def contains_punctuation(self, sentence: str):
        punctuation_pattern = r"([.,;:?!]) "
        matches = list(re.finditer(punctuation_pattern, sentence))
        if matches and len(sentence.split()) > 4:
            last_match = matches[-1]  # Get the last match
            before_punctuation = sentence[: last_match.start()]
            punctuation = last_match.group(1)
            after_punctuation = sentence[last_match.end() :]
            return before_punctuation + punctuation, after_punctuation

        else:
            return None, None

    async def greet(self):
        await self.websocket_handler.send_mark("not_listening")
        greeting = self.config.get("greeting_message") or """Hola! Mi nombre es Robotino, nos comunicamos de azul-Mar-e. 
            ¿Con quién tengo el gusto de hablar?
        """

        timestamp = datetime.now(MEXICO_TZ).strftime("[%Y-%m-%d %H:%M:%S]")  # ✅ Zona horaria de México
        self.log(f"GREETING at {timestamp}: {greeting}")
        await self.synthesize_and_send(greeting)
        self.llm_service.add_to_conversation("assistant", greeting)
        await self.websocket_handler.send_mark("listening")
