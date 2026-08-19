import json
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
        self.registered_functions_by_name = {
            func.__name__: func
            for func in self.function_manager.registered_functions
        }
        self.pending_tool_calls: dict[int, dict[str, Any]] = {}
        # if self.config.get("use_kb"):
        #     self.vectorbase = VectorBase(config.get("agent_name", None))

    def _preview_text(self, value: Any, limit: int = 400) -> str:
        if value is None:
            return ""
        text = value if isinstance(value, str) else str(value)
        text = text.replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

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

    def seed_conversation_history(self, messages: list[dict[str, Any]]) -> None:
        """
        Reemplaza el historial no-system por mensajes ya estructurados.
        Mantiene intacto el system prompt actual del servicio.
        """
        system_messages = [
            msg for msg in self.conversation_history
            if msg.get("role") == "system"
        ]

        seeded_messages = []
        for message in messages:
            role = message.get("role")
            if role == "system":
                # El system prompt efectivo se controla al construir el servicio.
                continue

            seeded_messages.append(
                {
                    "role": role,
                    "content": self.ensure_valid_message_content(
                        message.get("content", "")
                    ),
                }
            )

        self.conversation_history = system_messages + seeded_messages

    async def generate_response(self, user_input: str) -> AsyncGenerator[str, None]:
        if self.config.get("use_kb"):
            kb_context = self.vectorbase.Query(user_input)
            user_input = f"Context:\n{kb_context}\n\nQuery:\n{user_input}"
        
        self.add_to_conversation("user", user_input)
        logger.critical(
            "🧠 [LLM TRACE] start model=%s history_messages=%s user_input=%s",
            "gpt-5.4-mini-2026-03-17",
            len(self.conversation_history),
            self._preview_text(user_input),
        )
        
        # Verifica si es necesario resumir el contexto
        if self.config.get("use_context_summarization", False) and len(self.conversation_history) > self.config.get("summarize_threshold", 15):
            await self.summarize_conversation_history()
            
        max_tool_rounds = int(self.config.get("max_tool_rounds", 8))
        tool_round = 0

        while True:
            self.pending_tool_calls = {}
            generator = await self.llm_generator()

            full_message = ""
            finish_reason = None

            async for chunk in generator:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if delta.tool_calls:
                    self.handle_tool_call(delta.tool_calls)

                if delta.content:
                    yield delta.content
                    full_message += delta.content

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            if self.pending_tool_calls:
                tool_round += 1

                if tool_round > max_tool_rounds:
                    raise RuntimeError(
                        "Se excedió el máximo de "
                        f"{max_tool_rounds} rondas de tools."
                    )

                await self.handle_tool_call_finish(
                    assistant_content=full_message
                )
                continue

            if full_message:
                self.add_to_conversation("assistant", full_message)
                logger.critical(
                    "🧠 [LLM TRACE] final_response finish_reason=%s tool_rounds=%s response=%s",
                    finish_reason,
                    tool_round,
                    self._preview_text(full_message),
                )
            elif finish_reason not in (None, "stop"):
                logger.warning(
                    "El modelo terminó sin contenido. finish_reason=%s",
                    finish_reason,
                )

            break

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
                model="gpt-5.4-mini-2026-03-17",  # Puedes cambiar el modelo si es necesario
                #model=self.config.get("model") or "gpt-3.5-turbo-1106",
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
        model = "gpt-5.4-mini-2026-03-17"
        #model = self.config.get("model") or "gpt-5.4-mini-2026-03-17"
        
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
                #temperature=0.1,
                tools=self.function_manager.get_function_definition(),
            )
        return generator

    def handle_tool_call(self, tool_call_chunks) -> None:
        for tool_call in tool_call_chunks:
            index = tool_call.index

            if index not in self.pending_tool_calls:
                self.pending_tool_calls[index] = {
                    "id": None,
                    "type": "function",
                    "function": {
                        "name": "",
                        "arguments": "",
                    },
                }

            current = self.pending_tool_calls[index]

            if tool_call.id:
                current["id"] = tool_call.id

            if tool_call.type:
                current["type"] = tool_call.type

            if tool_call.function:
                if tool_call.function.name:
                    current["function"]["name"] = tool_call.function.name

                if tool_call.function.arguments:
                    current["function"]["arguments"] += tool_call.function.arguments

    def _get_complete_tool_calls(self) -> list[dict[str, Any]]:
        tool_calls = []

        for index in sorted(self.pending_tool_calls):
            tool_call = self.pending_tool_calls[index]
            tool_call_id = tool_call.get("id")
            function_name = tool_call.get("function", {}).get("name")
            arguments = tool_call.get("function", {}).get("arguments", "")

            if not tool_call_id:
                raise RuntimeError(
                    f"Tool call index={index} llegó sin tool_call.id."
                )

            if not function_name:
                raise RuntimeError(
                    f"Tool call index={index} llegó sin function.name."
                )

            tool_calls.append(
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": arguments,
                    },
                }
            )

        return tool_calls

    async def handle_tool_call_finish(
        self,
        assistant_content: str = "",
    ) -> None:
        tool_calls = self._get_complete_tool_calls()

        self.conversation_history.append(
            {
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": tool_calls,
            }
        )

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            function_name = tool_call["function"]["name"]
            raw_arguments = tool_call["function"]["arguments"]

            logger.debug(
                "Call id=%s: %s with arguments: %s",
                tool_call_id,
                function_name,
                raw_arguments,
            )
            logger.critical(
                "🧠 [LLM TRACE] tool_selected id=%s name=%s args=%s assistant_context=%s",
                tool_call_id,
                function_name,
                self._preview_text(raw_arguments),
                self._preview_text(assistant_content),
            )

            try:
                arguments = json.loads(raw_arguments or "{}")
            except json.decoder.JSONDecodeError as e:
                logger.error(
                    "Error decoding JSON for function %s: %s Input was: %s.",
                    function_name,
                    e,
                    raw_arguments,
                )
                self.conversation_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": (
                            "Error: argumentos JSON inválidos para "
                            f"{function_name}: {str(e)}"
                        ),
                    }
                )
                continue

            func = self.registered_functions_by_name.get(function_name)
            if func is None:
                self.conversation_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": (
                            f"Error: la función '{function_name}' no está registrada."
                        ),
                    }
                )
                continue

            try:
                response = await func(**arguments)
                tool_response = self.ensure_valid_message_content(response)
            except Exception as e:
                logger.error(
                    "Error calling function %s with arguments %s: %s",
                    function_name,
                    arguments,
                    e,
                )
                tool_response = (
                    f"Error ejecutando '{function_name}': {str(e)}"
                )

            logger.critical(
                "🧠 [LLM TRACE] tool_result id=%s name=%s result=%s",
                tool_call_id,
                function_name,
                self._preview_text(tool_response),
            )

            self.conversation_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_response,
                }
            )

    def clear_conversation_history(self) -> None:
        """Limpia el historial de conversación pero conserva los mensajes del sistema"""
        # Extraer los mensajes del sistema
        system_messages = [msg for msg in self.conversation_history if msg["role"] == "system"]
        
        # Limpiar el historial
        self.conversation_history = []
        
        # Restaurar los mensajes del sistema
        self.conversation_history.extend(system_messages)
