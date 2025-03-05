import json
import asyncio
import openai
from app.util.logger import logger
from typing import Any, AsyncGenerator
from .llm_service import LLMService
from app.util.database import VectorBase
from app.services.functions.function_manager import FunctionManager


class OpenAIService(LLMService):
    def __init__(
        self,
        config,
        api_key: str | None,
        function_manager: FunctionManager,
        system: str = ""
    ):
        self.config = config
        self.client = openai.AsyncClient(api_key=api_key)
        self.conversation_history = [{"role": "system", "content": system}]
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None
        if self.config.get("use_kb"):
            self.vectorbase = VectorBase(config.get("agent_name", None))

    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        self.conversation_history.append({"role": role, "content": content, **kwargs})

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        """Genera la respuesta del modelo en streaming, evitando pausas perceptibles."""
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"

        self.add_to_conversation("user", user_input)
        generator = await self.llm_generator()

        full_message = ""
        buffer = ""  # Acumulador de tokens antes de enviarlos

        async for chunk in generator:
            content = chunk.choices[0].delta.content

            # 🚀 Detecta el final cuando content es None
            if content is None:
                break  # Finaliza el bucle si no hay más contenido

            buffer += content

            # Enviar contenido acumulado en el buffer si alcanza cierto tamaño
            if len(buffer) > 20:  # Ajusta el umbral según necesidad
                yield buffer
                full_message += buffer
                buffer = ""  # Limpiar el buffer

        # Enviar cualquier contenido restante en el buffer
        if buffer:
            yield buffer
            full_message += buffer

        if full_message:
            self.add_to_conversation("assistant", full_message)

    async def llm_generator(self):
        """Genera respuesta de OpenAI en streaming para reducir la latencia."""
        self.conversation_history = [
            msg for msg in self.conversation_history if msg.get("content") is not None
        ]
        generator = await self.client.chat.completions.create(
            model=self.config.get("model") or "gpt-4-0125-preview",
            messages=self.conversation_history,
            stream=True,  # 🚀 Ahora en streaming con detección de fin
            tool_choice="auto",
            temperature=0.1,
            max_tokens=100,
            tools=self.function_manager.get_function_definition(),
        )
        return generator

    async def handle_tool_call(self, tool_call_chunk):
        """Maneja las llamadas a herramientas asegurando que solo se ejecuten cuando sea necesario."""
        tool_call = tool_call_chunk[0]

        if not tool_call.function or not tool_call.function.name:
            return  # ❌ No ejecutar si no hay función válida

        function_name = tool_call.function.name
        arguments_chunk = tool_call.function.arguments or ""

        if function_name:
            self.current_function_name = function_name
            self.functions[self.current_function_name] = "" 

        if self.current_function_name:
            self.functions[self.current_function_name] += arguments_chunk

    async def handle_tool_call_finish(self):
        """Ejecuta las funciones registradas en paralelo para mejorar la eficiencia."""
        tasks = []

        for k, v in self.functions.items():
            logger.debug(f"Call: {k} with arguments: {v}")

            try:
                arguments = json.loads(v)
                call_sid = str(arguments.get("call_sid", ""))
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for function {k}: {e}. Input was: {v}.")
                continue

            for func in self.function_manager.registered_functions:
                if func.__name__ == k:
                    tasks.append(self.execute_function(func, call_sid))

        if tasks:
            responses = await asyncio.gather(*tasks)  # 🔄 Ejecutar funciones en paralelo
            for response in responses:
                if response:
                    yield response

        self.functions = {}
        self.current_function_name = None

    async def execute_function(self, func, call_sid):
        """Ejecuta la función de manera asincrónica y maneja errores."""
        try:
            response = await func(call_sid=f'"{call_sid}"')
            self.add_to_conversation("function", content=response, name=func.__name__)
            return response
        except Exception as e:
            logger.error(f"Error calling function {func.__name__} with call_sid {call_sid}: {e}")
            return None

    def clear_conversation_history(self) -> None:
        """Limpia el historial de conversación para resetear el contexto."""
        self.conversation_history = []
