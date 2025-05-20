import json
import time
import openai
import os
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
        
        # ADD THIS: Ensure API key has sk- prefix
        if api_key and not api_key.startswith("sk-"):
            api_key = f"sk-{api_key}"
        
        self.api_key = api_key
        
        # Initialize with DeepSeek's endpoint
        self.client = openai.AsyncClient(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )
        
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": self.ensure_valid_message_content(system)})
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None
        
        # Log initialization (without exposing full key)
        if api_key:
            key_preview = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "too_short"
            logger.debug(f"DeepSeekService initialized with API key preview: {key_preview}")
        else:
            logger.error("DeepSeekService initialized with empty API key")

    def ensure_valid_message_content(self, content):
        """
        Asegura que el contenido del mensaje esté en un formato válido para la API.
        """
        if content is None:
            return ""
        
        if isinstance(content, str):
            return content
        
        if isinstance(content, (dict, list, tuple, set)):
            return str(content)
        
        return str(content)
    
    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        """Añadir mensaje al historial con optimización de contexto"""
        validated_content = self.ensure_valid_message_content(content)
        
        # For DeepSeek API compatibility:
        # Convert 'function' role to 'tool' role if needed
        if role == "function":
            role = "tool"
            # Make sure tool_call_id is present if using 'tool' role
            if 'name' in kwargs and 'tool_call_id' not in kwargs:
                kwargs['tool_call_id'] = kwargs['name']
        
        self.conversation_history.append({"role": role, "content": validated_content, **kwargs})
        
        max_messages = self.config.get("max_context_messages", 20)
        if len(self.conversation_history) > max_messages + 1:
            system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
            recent_messages = self.conversation_history[-(max_messages - len(system_messages)):]
            self.conversation_history = system_messages + recent_messages

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        self.add_to_conversation("user", user_input)
        self.sanitize_messages_for_deepseek()
        logger.debug("Sending to DeepSeek: %s", 
                 json.dumps([{k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else str(v)) 
                             for k, v in msg.items()}
                            for msg in self.conversation_history[:5]]))
        # First API call to get potential tool calls
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            initial_response = await self.client.chat.completions.create(
                model=self.config.get("deepseek_model", "deepseek-chat"),
                messages=self.conversation_history,
                temperature=0.7,
                tools=self.function_manager.get_function_definition(),
                extra_headers=headers
            )
            
            assistant_message = initial_response.choices[0].message
            
            # Check if there are tool calls
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                # Add assistant's response with tool_calls to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in assistant_message.tool_calls
                    ]
                })
                
                # Process each tool call
                for tool_call in assistant_message.tool_calls:
                    try:
                        func_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        
                        # Find and execute the function
                        for func in self.function_manager.registered_functions:
                            if func.__name__ == func_name:
                                result = await func(**args)
                                
                                # Add tool response with tool_call_id
                                self.conversation_history.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": result
                                })
                                break
                    except Exception as e:
                        error_msg = f"Error executing tool call {func_name}: {str(e)}"
                        logger.error(error_msg)
                        # Add error as tool response
                        self.conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Error: {error_msg}"
                        })
                
                # Make second API call with tool results
                final_response = await self.client.chat.completions.create(
                    model=self.config.get("deepseek_model", "deepseek-chat"),
                    messages=self.conversation_history,
                    temperature=0.7,
                    extra_headers=headers
                )
                
                final_content = final_response.choices[0].message.content
                yield final_content
                self.add_to_conversation("assistant", final_content)
                
            else:
                # No tool calls, just return the content
                content = assistant_message.content
                yield content
                self.add_to_conversation("assistant", content)
                
        except Exception as e:
            error_message = f"Error: {str(e)}"
            logger.error(error_message)
            yield error_message

    async def summarize_conversation_history(self):
        """Resumir el historial de conversación cuando se vuelve demasiado largo"""
        system_message = next((msg for msg in self.conversation_history if msg["role"] == "system"), None)
        
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" 
                                      for msg in self.conversation_history 
                                      if msg['role'] != "system"])
        
        summary_prompt = f"""Resume la siguiente conversación de manera concisa, preservando la información clave:
{conversation_text}
Proporciona un resumen breve pero completo que capture los puntos principales de la conversación."""
        
        try:
            # Use explicit headers
            api_key = self.api_key
            if not api_key.startswith("sk-"):
                api_key = f"sk-{api_key}"
                
            headers = {"Authorization": f"Bearer {api_key}"}
            
            summary_response = await self.client.chat.completions.create(
                model=self.config.get("deepseek_model", "deepseek-chat"),
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.1,
                extra_headers=headers
            )
            
            summary = summary_response.choices[0].message.content
            
            self.conversation_history = []
            
            if system_message:
                self.conversation_history.append(system_message)
                
            self.conversation_history.append(
                {"role": "system", "content": f"Resumen de la conversación anterior: {summary}"}
            )
            
            logger.debug(f"Historial de conversación resumido. Nuevo tamaño: {len(self.conversation_history)}")
            
        except Exception as e:
            error_msg = f"Error al resumir el historial de conversación: {str(e)}"
            logger.error(error_msg)
            self.add_to_conversation("system", "Nota: Parte del historial de conversación anterior ha sido eliminado para optimizar el rendimiento.")

    async def llm_generator(self):
        """Only used for simple queries without function calls"""
        model = self.config.get("deepseek_model", "deepseek-chat")
        
        try:
            self.sanitize_messages_for_deepseek()
            logger.debug("Sending to DeepSeek (llm_generator): %s", 
                     json.dumps([{k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else str(v)) 
                                 for k, v in msg.items()}
                                for msg in self.conversation_history[:5]]))
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            generator = await self.client.chat.completions.create(
                model=model,
                messages=self.conversation_history,
                stream=True,
                temperature=0.7,
                extra_headers=headers
            )
            return generator
        except Exception as err:
            error_message = f"Error calling DeepSeek API: {str(err)}"
            logger.error(error_message)
            
            # Safe error generator with properly scoped variables
            error_content = f"Error accessing API: {str(err)}"
            
            async def error_generator():
                yield type('obj', (object,), {
                    'choices': [type('obj', (object,), {
                        'delta': type('obj', (object,), {
                            'content': error_content
                        }),
                        'finish_reason': None
                    })]
                })
            return error_generator()

    async def handle_tool_call(self, tool_call_chunk):
        tool_call = tool_call_chunk[0]

        function_name = None
        if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name'):
            function_name = tool_call.function.name

        arguments_chunk = ""
        if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'arguments'):
            arguments_chunk = tool_call.function.arguments

        if function_name:
            self.current_function_name = function_name
            self.functions[self.current_function_name] = ""

        if self.current_function_name:
            self.functions[self.current_function_name] += arguments_chunk

    async def handle_tool_call_finish(self):
        for k, v in self.functions.items():
            logger.debug(f"Call: {k} with arguments: {v}")
            
            try:
                self.sanitize_messages_for_deepseek()
                logger.debug("Sending to DeepSeek (handle_tool_call_finish): %s", 
                     json.dumps([{k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else str(v)) 
                                 for k, v in msg.items()}
                                for msg in self.conversation_history[:5]]))
                arguments = json.loads(v)
            except json.decoder.JSONDecodeError as e:
                error_message = f"Error decoding JSON for function {k}: {e}"
                if hasattr(e, 'message'):
                    error_message += f", {e.message}"
                error_message += f" Input was: {v}."
                logger.error(error_message)
                continue

            for func in self.function_manager.registered_functions:
                if func.__name__ == k:
                    try:
                        response = await func(**arguments)
                    except Exception as e:
                        logger.error(f"Error calling function {k} with arguments {arguments}: {str(e)}")
                        continue
                    
                    # CHANGE THIS LINE: Use "tool" role instead of "function" for DeepSeek
                    self.add_to_conversation(
                        "tool", content=response, name=func.__name__, tool_call_id=k
                    )

        try:
            # Important: Use explicit headers here too
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            generator = await self.client.chat.completions.create(
                model=self.config.get("deepseek_model", "deepseek-chat"),
                messages=self.conversation_history,
                stream=True,
                temperature=0.7,
                tools=self.function_manager.get_function_definition(),
                extra_headers=headers
            )

            full_message = ""
            async for chunk in generator:
                content = chunk.choices[0].delta.content if hasattr(chunk.choices[0].delta, 'content') else None
                if content:
                    yield content
                    full_message += content

            self.add_to_conversation("assistant", full_message)
        except Exception as local_e:
            error_content = f"Error in handle_tool_call_finish: {str(local_e)}"
            logger.error(error_content)
            yield error_content
        finally:
            self.functions = {}
            self.current_function_name = None

    def clear_conversation_history(self) -> None:
        """Limpia el historial de conversación pero conserva los mensajes del sistema"""
        system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
        self.conversation_history = []
        self.conversation_history.extend(system_messages)

    def sanitize_messages_for_deepseek(self):
        """
        Ensures all messages are properly formatted for DeepSeek API.
        DeepSeek requires all message content to be strings.
        """
        for i, message in enumerate(self.conversation_history):
            # Ensure content is always a string
            if "content" in message and not isinstance(message["content"], str):
                # Convert complex objects to string representation
                if message["content"] is None:
                    message["content"] = ""
                else:
                    message["content"] = str(message["content"])
                    
            # Remove any unsupported fields that aren't expected in the message format
            allowed_keys = ["role", "content", "tool_call_id", "tool_calls"]
            for key in list(message.keys()):
                if key not in allowed_keys:
                    del message[key]