import logging
import re

from app.services.stt.stt_service import STTService
from app.services.llm.llm_service import LLMService
from app.services.tts.tts_service import TTSService
from app.api.websocket_handler import WebSocketHandler


class Orchestrator:
    def __init__(
        self,
        websocket_handler: WebSocketHandler,
        stt_service: STTService,
        llm_service: LLMService,
        tts_service: TTSService,
    ):
        self.stt_service = stt_service
        self.llm_service = llm_service
        self.tts_service = tts_service
        self.websocket_handler = websocket_handler

    async def process_audio_stream(self):
        await self.greet()

        await self.stt_service.start_transcription()
        await self.stt_service.set_transcript_received_callback(self.handler)

        async for audio_chunk in self.websocket_handler.process_stream():
            await self.stt_service.transcribe(audio_chunk)
        await self.stt_service.finish_transcription()

    async def handler(self, transcription: dict) -> None:
        if self.websocket_handler.is_connected and transcription.get("channel"):
            full_transcript = transcription["channel"]["alternatives"][0]["transcript"]
            if full_transcript:
                logging.getLogger("uvicorn").info(f"CUSTOMER: {full_transcript}")
                await self.websocket_handler.send_mark("not_listening")
                await self.process_transcript(full_transcript)
                await self.websocket_handler.send_mark("listening")

    async def process_transcript(self, transcript: str) -> None:
        buffer = ""
        generator = self.llm_service.generate_response(transcript)

        async for token in generator:  # type:ignore
            if not self.websocket_handler.is_connected:
                buffer = ""
                break
            buffer += token
            buffer = await self.process_buffer(buffer)

        if buffer:
            await self.synthesize_and_send(buffer)

    async def process_buffer(self, buffer: str) -> str:
        sentence, remainder = self.contains_punctuation(buffer)
        if sentence and remainder:
            await self.synthesize_and_send(sentence)
            return remainder
        return buffer

    async def synthesize_and_send(self, text: str) -> None:
        logging.getLogger("uvicorn").info(f"MODEL: {text}")
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
        greeting = """ ¡Hola! Soy Cosme Diante de Zagar Comedy Bar. ¿Cómo puedo ayudarte hoy?
        """
        await self.synthesize_and_send(greeting)
        self.llm_service.add_to_conversation("assistant", greeting)
        await self.websocket_handler.send_mark("listening")