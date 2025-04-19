import json
import time
import openai
from app.util.logger import logger
from typing import Any, AsyncGenerator
from .llm_service import LLMService
# from app.util.database import VectorBase
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
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": self.ensure_valid_message_content(system)})
        self.function_manager = function_manager
        self.functions = {}
        self.current_function_name = None
        # if self.config.get("use_kb"):
        #     self.vectorbase = VectorBase(config.get("agent_name", None))
    def ensure_valid_message_content(self, content):
        """
        Asegura que el contenido del mensaje esté en un formato válido para la API de OpenAI.
        La API espera que content sea un string o un array de objetos.
        
        Args:
            content: El contenido del mensaje a validar
            
        Returns:
            El contenido en un formato válido
        """
        # Si es None, convertirlo a string vacío
        if content is None:
            return ""
        
        # Si ya es un string, devolverlo como está
        if isinstance(content, str):
            return content
        
        # Si es un diccionario o cualquier otro objeto, convertirlo a string
        if isinstance(content, (dict, list, tuple, set)):
            return str(content)
        
        # Para cualquier otro tipo, convertir a string
        return str(content)
    
    def add_to_conversation(self, role: str, content: str, **kwargs: Any) -> None:
        """Añadir mensaje al historial con optimización de contexto"""
        # Aplicar ensure_valid_message_content al contenido
        validated_content = self.ensure_valid_message_content(content)
        
        self.conversation_history.append({"role": role, "content": validated_content, **kwargs})
        
        # Verificar si el historial ha crecido demasiado
        max_messages = self.config.get("max_context_messages", 20)  # Configurable
        if len(self.conversation_history) > max_messages + 1:  # +1 para el mensaje del sistema
            # Extraer los mensajes del sistema
            system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
            
            # Mantener solo los mensajes más recientes
            recent_messages = self.conversation_history[-(max_messages - len(system_messages)):]
            
            # Reorganizar el historial: primero mensajes del sistema, luego los recientes
            self.conversation_history = system_messages + recent_messages

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"
        
        self.add_to_conversation("user", user_input)
        
        # Verifica si es necesario resumir el contexto
        if self.config.get("use_context_summarization", False) and len(self.conversation_history) > self.config.get("summarize_threshold", 15):
            await self.summarize_conversation_history()
            
        generator = await self.llm_generator()

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

    async def summarize_conversation_history(self):
        """Resumir el historial de conversación cuando se vuelve demasiado largo"""
        # Extraer el mensaje del sistema original
        system_message = next((msg for msg in self.conversation_history if msg["role"] == "system"), None)
        
        # Preparar el contenido para ser resumido
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" 
                                      for msg in self.conversation_history 
                                      if msg['role'] != "system"])
        
        summary_prompt = f"""Resume la siguiente conversación de manera concisa, preservando la información clave:

{conversation_text}



Proporciona un resumen breve pero completo que capture los puntos principales de la conversación.
"""
        
        try:
            # Crear una solicitud separada para resumir el contexto
            summary_response = await self.client.chat.completions.create(
                model=self.config.get("model") or "gpt-3.5-turbo-1106",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.1,
            )
            
            summary = summary_response.choices[0].message.content
            
            # Reiniciar el historial con el sistema original y el resumen
            self.conversation_history = []
            
            # Restaurar el mensaje del sistema si existía
            if system_message:
                self.conversation_history.append(system_message)
                
            # Añadir el resumen como contexto
            self.conversation_history.append(
                {"role": "system", "content": f"Resumen de la conversación anterior: {summary}"}
            )
            
            logger.debug(f"Historial de conversación resumido. Nuevo tamaño: {len(self.conversation_history)}")
            
        except Exception as e:
            logger.error(f"Error al resumir el historial de conversación: {str(e)}")
            # Si falla el resumen, aplicar la estrategia de ventana deslizante
            self.add_to_conversation("system", "Nota: Parte del historial de conversación anterior ha sido eliminado para optimizar el rendimiento.")

    async def llm_generator(self):
        # Usar o3-mini si está configurado
        model = self.config.get("model") or "gpt-3.5-turbo-1106"
        
        # Comprobar si estamos usando un modelo de razonamiento (o3-mini)
        if model == "o3-mini":
            # Si es un modelo de razonamiento, incluir el parámetro reasoning_effort
            generator = await self.client.chat.completions.create(
                model=model,
                messages=self.conversation_history,
                stream=True,
                reasoning_effort=self.config.get("reasoning_effort", "medium"),
                tool_choice="auto",
                tools=self.function_manager.get_function_definition(),
            )
        else:
            # Para modelos regulares, incluir temperature
            generator = await self.client.chat.completions.create(
                model=model,
                messages=self.conversation_history,
                stream=True,
                tool_choice="auto",
                temperature=0.1,
                tools=self.function_manager.get_function_definition(),
            )
        return generator

    async def handle_tool_call(self, tool_call_chunk):
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
        """Limpia el historial de conversación pero conserva los mensajes del sistema"""
        # Extraer los mensajes del sistema
        system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
        
        # Limpiar el historial
        self.conversation_history = []
        
        # Restaurar los mensajes del sistema
        self.conversation_history.extend(system_messages)