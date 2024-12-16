import json
import time
from typing import Any, AsyncGenerator
from app.util.logger import logger
from .llm_service import LLMService
from app.util.database import VectorBase
from app.services.functions.function_manager import FunctionManager

# Replace with the appropriate Gemini library import
#from gemini_client import AsyncGeminiClient  # Replace with actual library name
import google.generativeai as genai


class GeminiService(LLMService):
    def __init__(
        self,
        config,
        api_key: str | None,
        function_manager: FunctionManager,
        system: str = "",
    ):
        self.config = config
        # Configure the API key globally
        genai.configure(api_key="AIzaSyCffsxNS45NvX5ni8MMrj7ERKy4lehWq6w")

        # Create a GenerativeModel client
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")  # Replace with your model name
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": system})
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None
        if self.config.get("use_kb"):
            self.vectorbase = VectorBase(config.get("agent_name", None))

    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        self.conversation_history.append({"role": role, "content": content, **kwargs})

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"

        self.add_to_conversation("user", user_input)
        generator = await self.llm_generator()

        full_message = ""
        async for chunk in generator:
            tool_call = chunk.get("tool_calls")  # Replace with Gemini's response format
            if tool_call:
                await self.handle_tool_call(tool_call)

            if chunk.get("finish_reason") == "tool_calls":
                async for content in self.handle_tool_call_finish():
                    yield content

            content = chunk.get("content")  # Replace with Gemini's response format
            if content:
                yield content
                full_message += content

        if full_message:
            self.add_to_conversation("assistant", full_message)

    async def llm_generator(self):
        if not self.client:
            # Ensure client is initialized (if asynchronous)
            await self._initialize_client()

        generator = await self.client.chat_completions(
            model=self.config.get("model") or "gemini-2.0-flash-exp",
            messages=self.conversation_history,
            stream=True,
            temperature=0.1,
            # ... other arguments
        )
        return generator

async def _initialize_client(self):
    # Asynchronous initialization logic, if needed
    self.client = genai.GenerativeModel("gemini-2.0-flash-exp")

    async def handle_tool_call(self, tool_call_chunk):
        tool_call = tool_call_chunk[0]  # Assuming it's a list in Gemini

        function_name = None
        if tool_call.get("function") and tool_call["function"].get("name"):
            function_name = tool_call["function"]["name"]

        arguments_chunk = ""
        if tool_call.get("function") and tool_call["function"].get("arguments"):
            arguments_chunk = tool_call["function"]["arguments"]

        if function_name:
            self.current_function_name = function_name
            self.functions[self.current_function_name] = ""

        if self.current_function_name:
            self.functions[self.current_function_name] += arguments_chunk

    async def handle_tool_call_finish(self):
        for k, v in self.functions.items():
            logger.debug(f"Call: {k} with arguments: {v}")

            try:
                arguments = json.loads(v)
            except json.decoder.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for function {k}: {e},{e.message} Input was: {v}.")
                continue

            for func in self.function_manager.registered_functions:
                if func.__name__ == k:
                    try:
                        response = await func(**arguments)
                    except Exception as e:
                        logger.error(f"Error calling function {k} with arguments {arguments}: {e}")
                        continue
                    
                    self.add_to_conversation(
                        "function", content=response, name=func.__name__
                    )

        generator = await self.llm_generator()

        full_message = ""
        async for chunk in generator:
            content = chunk.choices[0].delta.content
            if content:
                yield content
                full_message += content

        self.add_to_conversation("assistant", full_message)
        self.functions = {}
        self.current_function_name = None

    def clear_conversation_history(self) -> None:
        self.conversation_history = []