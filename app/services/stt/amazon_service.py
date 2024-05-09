import asyncio
import logging
import time
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.model import TranscriptEvent
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from app.services.stt.stt_service import STTService
from amazon_transcribe.model import (
    TranscriptEvent,
    StartStreamTranscriptionEventStream,
)


class AmazonTranscribeService(STTService):
    def __init__(self, region, language="en-US", sample_rate=8000, enhanced=True):
        self.client = TranscribeStreamingClient(region="us-west-2")
        self.stream = None
        self.callback = None
        self.language = language
        self.sample_rate = sample_rate
        self.enhanced = enhanced
        self.stream: StartStreamTranscriptionEventStream | None = None

    async def start_transcription(self):
        self.stream = await self.client.start_stream_transcription(
            language_code=self.language,
            media_sample_rate_hz=8000,
            media_encoding="pcm",
            enable_partial_results_stabilization=False,
        )
        logging.getLogger("uvicorn").info(f"Correctly connected to Amazon Transcribe.")

    async def transcribe(self, audio_chunk):
        if self.stream:
            await self.stream.input_stream.send_audio_event(audio_chunk=audio_chunk)

    async def finish_transcription(self):
        if self.stream:
            await self.stream.input_stream.end_stream()

    async def set_transcript_received_callback(self, callback):
        self.callback = callback
        if self.stream:
            handler = MyEventHandler(
                self.stream.output_stream,
                self.callback,
                self.enhanced,
            )
            asyncio.create_task(handler.handle_events())


class MyEventHandler(TranscriptResultStreamHandler):
    def __init__(self, output_stream, callback, enhanced=False):
        super().__init__(output_stream)
        self.callback = callback
        self.buffer = ""
        self.last_time = time.perf_counter()
        self.enhanced = enhanced

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        if self.enhanced:
            await self.enhanced_handle(transcript_event)
        else:
            await self.simple_handle(transcript_event)

    async def simple_handle(self, transcript_event: TranscriptEvent):
        for result in transcript_event.transcript.results:
            if not result.is_partial and result.alternatives:
                transcript = result.alternatives[0].transcript
                if self.callback:
                    final_transcript = await self.normalize(transcript)
                    await self.callback(final_transcript)

    async def enhanced_handle(self, transcript_event: TranscriptEvent):
        if time.perf_counter() - self.last_time > 0.5 and self.buffer:
            final_transcript = await self.normalize(self.buffer)
            await self.callback(final_transcript)
            self.buffer = ""

        results = transcript_event.transcript.results

        for result in results:
            self.last_time = time.perf_counter()
            if result.is_partial:
                return

            if not result.alternatives:
                return

            transcript = result.alternatives[0].transcript
            self.buffer += transcript

            logging.getLogger("uvicorn").info(f"PARTIAL: {transcript}")

    async def normalize(self, transcript):
        final_transcript = {
            "type": "Results",
            "is_final": True,
            "speech_final": True,
            "channel": {
                "alternatives": [
                    {
                        "transcript": transcript,
                    }
                ]
            },
        }

        return final_transcript
