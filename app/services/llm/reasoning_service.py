import json
import openai
from app.util.logger import logger
from typing import Any, AsyncGenerator
from .llm_service import LLMService
from app.services.functions.function_manager import FunctionManager

class ReasoningService(LLMService):
    def __init__(
        self,
        config,
        api_key: str | None,
        function_manager: FunctionManager,
        system: str = ""
    ):
        self.config = config
        self.client = openai.AsyncClient(api_key=api_key)
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": system})
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None
        self.reasoning_effort = config.get("reasoning_effort", "medium")

    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        self.conversation_history.append({"role": role, "content": content, **kwargs})

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"
        
        self.add_to_conversation("user", user_input)
        
        # Usar la API estándar de chat.completions con el modelo o3-mini
        # y el parámetro reasoning_effort
        generator = await self.client.chat.completions.create(
            model=self.config.get("reasoning_model", "o3-mini"),
            messages=self.conversation_history,
            stream=True,
            reasoning_effort=self.reasoning_effort,  # Añadir el parámetro de esfuerzo de razonamiento
            tool_choice="auto",
            temperature=0.1,
            tools=self.function_manager.get_function_definition(),
        )
        
        full_message = ""
        async for chunk in generator:
            tool_call = chunk.choices[0].delta.tool_calls
            if tool_call:
                await self.handle_tool_call(tool_call)

            if chunk.choices[0].finish_reason == "tool_calls":
                async for content in self.handle_tool_call_finish():
                    yield content

            content = chunk.choices[0].delta.content
            if content:
                yield content
                full_message += content

        if full_message:
            self.add_to_conversation("assistant", full_message)