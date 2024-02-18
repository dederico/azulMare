from abc import ABC, abstractmethod
from typing import AsyncGenerator


class TTSService(ABC):
    stream_results: bool = False

    @abstractmethod
    async def synthesize(self, text: str):
        pass

    @abstractmethod
    async def stream_synthesize(self, text: str) -> AsyncGenerator[str, None]:
        pass