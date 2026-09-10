import json
import openai
import httpx
import asyncio
import os
from app.util.logger import logger
from typing import Any, AsyncGenerator
from .llm_service import LLMService
# from app.util.database import VectorBase
from app.services.functions.function_manager import FunctionManager


OPENAI_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=25.0)
OPENAI_MAX_RETRIES = 3
OPENAI_LOCAL_RETRY_ATTEMPTS = 2
OPENAI_LOCAL_RETRY_BACKOFF_SECONDS = 1.0
DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING_EFFORT = "high"
SUPPORTED_REASONING_EFFORTS = {
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}


class OpenAIService(LLMService):
    def __init__(
        self,
        config,
        api_key: str | None,
        function_manager: FunctionManager,
        system: str = ""
    ):
        self.config = config
        self.client = openai.AsyncClient(
            api_key=api_key,
            timeout=OPENAI_HTTP_TIMEOUT,
            max_retries=OPENAI_MAX_RETRIES,
        )
        self.conversation_history = []
        self.conversation_history.append({"role": "system", "content": self.ensure_valid_message_content(system)})
        self.function_manager = function_manager
        self.registered_functions_by_name = {
            func.__name__: func
            for func in self.function_manager.registered_functions
        }
        self.pending_tool_calls: dict[int, dict[str, Any]] = {}
        # Per-request evidence from official read-only knowledge functions.
        # The outbound policy uses it to preserve departmental phone numbers
        # that were actually returned by a tool instead of trusting the model.
        self.trusted_tool_outputs: list[str] = []
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

    def _serialize_for_log(self, value: Any, limit: int = 12000) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)

        if len(text) <= limit:
            return text

        return text[:limit] + f"... [truncated {len(text) - limit} chars]"

    def _log_tools_payload(self, model: str, tools_payload: list[dict[str, Any]]) -> None:
        tools_summary = []

        for tool in tools_payload:
            function_block = tool.get("function", {})
            tools_summary.append(
                {
                    "name": function_block.get("name"),
                    "description": function_block.get("description"),
                    "required": function_block.get("parameters", {}).get("required", []),
                }
            )

        logger.critical(
            "🧰 [TOOLS SUMMARY] model=%s tools_count=%s tools=%s",
            model,
            len(tools_summary),
            self._serialize_for_log(tools_summary, limit=8000),
        )
        logger.critical(
            "🧰 [TOOLS PAYLOAD] model=%s payload=%s",
            model,
            self._serialize_for_log(tools_payload),
        )

    def _is_retryable_connectivity_error(self, error: Exception) -> bool:
        return (
            isinstance(error, httpx.TimeoutException)
            or isinstance(error, openai.APITimeoutError)
            or isinstance(error, openai.APIConnectionError)
            or "ConnectTimeout" in type(error).__name__
        )

    def _reasoning_effort(self) -> str:
        configured = (
            os.getenv("OPENAI_REASONING_EFFORT")
            or self.config.get("reasoning_effort")
            or DEFAULT_REASONING_EFFORT
        )
        normalized = str(configured).strip().lower()
        if normalized not in SUPPORTED_REASONING_EFFORTS:
            logger.warning(
                "OPENAI_REASONING_EFFORT=%s no es válido; usando %s",
                configured,
                DEFAULT_REASONING_EFFORT,
            )
            return DEFAULT_REASONING_EFFORT
        return normalized

    async def _create_chat_completion_with_local_retry(self, **kwargs: Any):
        last_error: Exception | None = None

        for attempt in range(1, OPENAI_LOCAL_RETRY_ATTEMPTS + 1):
            try:
                if attempt > 1:
                    logger.warning(
                        "🔁 [OPENAI RETRY] attempt=%s/%s model=%s",
                        attempt,
                        OPENAI_LOCAL_RETRY_ATTEMPTS,
                        kwargs.get("model"),
                    )
                return await self.client.chat.completions.create(**kwargs)
            except Exception as error:
                last_error = error
                retryable = self._is_retryable_connectivity_error(error)
                logger.warning(
                    "⚠️ [OPENAI REQUEST FAILURE] attempt=%s/%s model=%s retryable=%s error_type=%s error=%s",
                    attempt,
                    OPENAI_LOCAL_RETRY_ATTEMPTS,
                    kwargs.get("model"),
                    retryable,
                    type(error).__name__,
                    str(error),
                )

                if not retryable or attempt >= OPENAI_LOCAL_RETRY_ATTEMPTS:
                    raise

                await asyncio.sleep(OPENAI_LOCAL_RETRY_BACKOFF_SECONDS)

        if last_error is not None:
            raise last_error

        raise RuntimeError("Fallo inesperado creando chat completion")

    async def _create_response_with_local_retry(self, **kwargs: Any):
        """Create a Responses API request with the same connectivity retry policy."""
        last_error: Exception | None = None

        for attempt in range(1, OPENAI_LOCAL_RETRY_ATTEMPTS + 1):
            try:
                if attempt > 1:
                    logger.warning(
                        "🔁 [OPENAI RESPONSES RETRY] attempt=%s/%s model=%s",
                        attempt,
                        OPENAI_LOCAL_RETRY_ATTEMPTS,
                        kwargs.get("model"),
                    )
                return await self.client.responses.create(**kwargs)
            except Exception as error:
                last_error = error
                retryable = self._is_retryable_connectivity_error(error)
                logger.warning(
                    "⚠️ [OPENAI RESPONSES FAILURE] attempt=%s/%s model=%s "
                    "retryable=%s error_type=%s error=%s",
                    attempt,
                    OPENAI_LOCAL_RETRY_ATTEMPTS,
                    kwargs.get("model"),
                    retryable,
                    type(error).__name__,
                    str(error),
                )
                if not retryable or attempt >= OPENAI_LOCAL_RETRY_ATTEMPTS:
                    raise
                await asyncio.sleep(OPENAI_LOCAL_RETRY_BACKOFF_SECONDS)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Fallo inesperado creando response")
    
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
            "🧠 [LLM TRACE] start model=%s reasoning_effort=%s history_messages=%s user_input=%s",
            DEFAULT_OPENAI_MODEL,
            self._reasoning_effort(),
            # "gpt-5.4-mini-2026-03-17",
            len(self.conversation_history),
            self._preview_text(user_input),
        )
        
        # Verifica si es necesario resumir el contexto
        if self.config.get("use_context_summarization", False) and len(self.conversation_history) > self.config.get("summarize_threshold", 15):
            await self.summarize_conversation_history()
            
        full_message = await self._generate_response_via_responses()
        if full_message:
            self.add_to_conversation("assistant", full_message)
            yield full_message
        else:
            logger.warning("Responses API terminó sin contenido visible.")

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
            # Resumir también mediante Responses para no mezclar contratos de API.
            summary_response = await self._create_response_with_local_retry(
                model=DEFAULT_OPENAI_MODEL,
                instructions=(
                    "Resume conversaciones de forma fiel y concisa. Conserva datos "
                    "confirmados, folios, estado del reporte y decisiones del ciudadano."
                ),
                input=summary_prompt,
                reasoning={"effort": "low"},
                store=False,
            )

            summary = self._response_output_text(summary_response)
            if not summary:
                raise RuntimeError("Responses no devolvió un resumen visible")
            
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
        """Legacy Chat Completions generator retained only for compatibility tests."""
        model = DEFAULT_OPENAI_MODEL
        tools_payload = self.function_manager.get_function_definition()
        self._log_tools_payload(model, tools_payload)

        return await self._create_chat_completion_with_local_retry(
            model=model,
            messages=self.conversation_history,
            stream=True,
            reasoning_effort="none",
            tool_choice="auto",
            tools=tools_payload,
        )

    @staticmethod
    def _item_value(item: Any, key: str, default=None):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @staticmethod
    def _serialize_response_item(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        if hasattr(item, "model_dump"):
            return item.model_dump(exclude_none=True)
        if hasattr(item, "dict"):
            return item.dict(exclude_none=True)
        raise TypeError(f"Item de Responses API no serializable: {type(item).__name__}")

    def _responses_tools_payload(self) -> list[dict[str, Any]]:
        """Convert Chat Completions function schemas to Responses function tools."""
        result = []
        for tool in self.function_manager.get_function_definition():
            function = tool.get("function", {})
            result.append(
                {
                    "type": "function",
                    "name": function.get("name"),
                    "description": function.get("description") or "",
                    "parameters": function.get("parameters") or {
                        "type": "object",
                        "properties": {},
                    },
                    "strict": False,
                }
            )
        return result

    def _responses_instructions_and_input(self) -> tuple[str, list[dict[str, Any]]]:
        instruction_parts = []
        response_input = []
        for message in self.conversation_history:
            role = message.get("role")
            content = self.ensure_valid_message_content(message.get("content", ""))
            if role == "system":
                if content:
                    instruction_parts.append(content)
                continue
            if role in {"user", "assistant"}:
                response_input.append({"role": role, "content": content})
        return "\n\n".join(instruction_parts), response_input

    def _response_function_calls(self, response: Any) -> list[Any]:
        return [
            item
            for item in (self._item_value(response, "output", []) or [])
            if self._item_value(item, "type") == "function_call"
        ]

    def _response_output_text(self, response: Any) -> str:
        output_text = self._item_value(response, "output_text", "") or ""
        if output_text:
            return str(output_text)

        fragments = []
        for item in self._item_value(response, "output", []) or []:
            if self._item_value(item, "type") != "message":
                continue
            for content in self._item_value(item, "content", []) or []:
                if self._item_value(content, "type") == "output_text":
                    text = self._item_value(content, "text", "")
                    if text:
                        fragments.append(str(text))
        return "".join(fragments)

    async def _execute_response_tool_calls(self, calls: list[Any]) -> list[dict[str, Any]]:
        outputs = []
        for call in calls:
            call_id = self._item_value(call, "call_id")
            function_name = self._item_value(call, "name")
            raw_arguments = self._item_value(call, "arguments", "{}") or "{}"
            logger.critical(
                "🧠 [LLM TRACE] responses_tool_selected id=%s name=%s args=%s",
                call_id,
                function_name,
                self._preview_text(raw_arguments),
            )

            try:
                arguments = json.loads(raw_arguments)
            except json.decoder.JSONDecodeError as error:
                tool_response = (
                    f"Error: argumentos JSON inválidos para {function_name}: {error}"
                )
            else:
                func = self.registered_functions_by_name.get(function_name)
                if func is None:
                    tool_response = f"Error: la función '{function_name}' no está registrada."
                else:
                    try:
                        tool_response = self.ensure_valid_message_content(
                            await func(**arguments)
                        )
                        if str(function_name or "").startswith("get_"):
                            self.trusted_tool_outputs.append(tool_response)
                    except Exception as error:
                        logger.error(
                            "Error calling function %s with arguments %s: %s",
                            function_name,
                            arguments,
                            error,
                        )
                        tool_response = f"Error ejecutando '{function_name}': {error}"

            logger.critical(
                "🧠 [LLM TRACE] responses_tool_result id=%s name=%s result=%s",
                call_id,
                function_name,
                self._preview_text(tool_response),
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": tool_response,
                }
            )
        return outputs

    async def _generate_response_via_responses(self) -> str:
        model = DEFAULT_OPENAI_MODEL
        tools_payload = self._responses_tools_payload()
        self._log_tools_payload(
            model,
            [
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("parameters"),
                    },
                }
                for tool in tools_payload
            ],
        )
        instructions, response_input = self._responses_instructions_and_input()
        max_tool_rounds = int(self.config.get("max_tool_rounds", 8))

        for tool_round in range(max_tool_rounds + 1):
            response = await self._create_response_with_local_retry(
                model=model,
                instructions=instructions,
                input=response_input,
                reasoning={"effort": self._reasoning_effort()},
                tools=tools_payload,
                tool_choice="auto",
                parallel_tool_calls=False,
                store=False,
                include=["reasoning.encrypted_content"],
            )
            calls = self._response_function_calls(response)
            if not calls:
                full_message = self._response_output_text(response)
                logger.critical(
                    "🧠 [LLM TRACE] responses_final tool_rounds=%s response=%s",
                    tool_round,
                    self._preview_text(full_message),
                )
                return full_message

            if tool_round >= max_tool_rounds:
                raise RuntimeError(
                    f"Se excedió el máximo de {max_tool_rounds} rondas de tools."
                )

            response_input.extend(
                self._serialize_response_item(item)
                for item in (self._item_value(response, "output", []) or [])
            )
            response_input.extend(await self._execute_response_tool_calls(calls))

        raise RuntimeError("Responses API terminó sin producir una respuesta")

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
