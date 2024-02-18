from abc import ABC, abstractmethod
from typing import AsyncGenerator


class LLMService(ABC):
    @abstractmethod
    def add_to_conversation(self, role: str, content: str) -> None:
        pass

    @abstractmethod
    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    def clear_conversation_history(self) -> None:
        pass