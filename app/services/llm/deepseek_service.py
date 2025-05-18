import json
import time
import httpx  # Using httpx for async HTTP requests
from app.util.logger import logger
from typing import Any, AsyncGenerator
from .llm_service import LLMService
from app.services.functions.function_manager import FunctionManager


class DeepSeekService(LLMService):
    def __init__(
        self,
        config,
        api_key: str | None,
        function_manager: FunctionManager,
        system: str = ""
    ):
        self.config = config
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"  # Verify this with DeepSeek's docs
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": self.ensure_valid_message_content(system)})
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None

    def ensure_valid_message_content(self, content):
        """Same as OpenAI version - no changes needed"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, (dict, list, tuple, set)):
            return str(content)
        return str(content)
    
    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        """Same as OpenAI version - no changes needed"""
        validated_content = self.ensure_valid_message_content(content)
        self.conversation_history.append({"role": role, "content": validated_content, **kwargs})
        
        max_messages = self.config.get("max_context_messages", 20)
        if len(self.conversation_history) > max_messages + 1:
            system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
            recent_messages = self.conversation_history[-(max_messages - len(system_messages)):]
            self.conversation_history = system_messages + recent_messages

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        """Modified for DeepSeek API"""
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"
        
        self.add_to_conversation("user", user_input)
        
        if self.config.get("use_context_summarization", False) and len(self.conversation_history) > self.config.get("summarize_threshold", 15):
            await self.summarize_conversation_history()
            
        async for chunk in self.llm_generator():
            # DeepSeek's streaming format may differ - adjust according to their API
            if "tool_calls" in chunk.choices[0].delta:
                await self.handle_tool_call(chunk.choices[0].delta.tool_calls)
            
            if chunk.choices[0].finish_reason == "tool_calls":
                async for content in self.handle_tool_call_finish():
                    yield content

            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def summarize_conversation_history(self):
        """Modified for DeepSeek API"""
        system_message = next((msg for msg in self.conversation_history if msg["role"] == "system"), None)
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" 
                                    for msg in self.conversation_history 
                                    if msg['role'] != "system"])
        
        summary_prompt = f"Resume la siguiente conversación... (same as before)"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.config.get("model") or "deepseek-chat",
                        "messages": [{"role": "user", "content": summary_prompt}],
                        "temperature": 0.1
                    }
                )
                response.raise_for_status()
                summary = response.json()["choices"][0]["message"]["content"]
                
                self.conversation_history = []
                if system_message:
                    self.conversation_history.append(system_message)
                self.conversation_history.append(
                    {"role": "system", "content": f"Resumen de la conversación anterior: {summary}"}
                )
                
        except Exception as e:
            logger.error(f"Error al resumir el historial: {str(e)}")
            self.add_to_conversation("system", "Nota: Parte del historial fue eliminado para optimizar el rendimiento.")

    async def llm_generator(self):
        """Modified for DeepSeek streaming API"""
        model = self.config.get("model") or "deepseek-chat"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"  # For streaming
                },
                json={
                    "model": model,
                    "messages": self.conversation_history,
                    "stream": True,
                    "temperature": 0.1,
                    "tools": self.function_manager.get_function_definition(),
                    "tool_choice": "auto"
                },
                timeout=60.0
            )
            
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        yield chunk
                    except json.JSONDecodeError:
                        continue

    async def handle_tool_call(self, tool_call_chunk):
        """Same logic, but may need to adjust for DeepSeek's format"""
        tool_call = tool_call_chunk[0]
        function_name = None
        
        if tool_call.function and tool_call.function.name:
            function_name = tool_call.function.name

        arguments_chunk = ""
        if tool_call.function.arguments:
            arguments_chunk = tool_call.function.arguments

        if function_name:
            self.current_function_name = function_name
            self.functions[self.current_function_name] = ""

        if self.current_function_name:
            self.functions[self.current_function_name] += arguments_chunk

    async def handle_tool_call_finish(self):
        """Same logic as before"""
        for k, v in self.functions.items():
            logger.debug(f"Call: {k} with arguments: {v}")
            
            try:
                arguments = json.loads(v)
            except json.decoder.JSONDecodeError as e:
                logger.error(f"Error decoding JSON for function {k}: {e}")
                continue

            for func in self.function_manager.registered_functions:
                if func.__name__ == k:
                    try:
                        response = await func(**arguments)
                    except Exception as e:
                        logger.error(f"Error calling function {k}: {e}")
                        continue
                    
                    self.add_to_conversation(
                        "function", content=response, name=func.__name__
                    )

        async for chunk in self.llm_generator():
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

        self.functions = {}
        self.current_function_name = None

    def clear_conversation_history(self) -> None:
        """Same as before"""
        system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
        self.conversation_history = []
        self.conversation_history.extend(system_messages)