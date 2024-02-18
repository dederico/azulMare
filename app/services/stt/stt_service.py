from abc import ABC, abstractmethod


class STTService(ABC):
    @abstractmethod
    async def start_transcription(self, *args, **kwargs):
        pass

    @abstractmethod
    async def transcribe(self, audio_chunk):
        pass

    @abstractmethod
    async def finish_transcription(self):
        pass

    @abstractmethod
    async def set_transcript_received_callback(self, callback):
        pass