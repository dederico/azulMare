import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

if "app.util.logger" not in sys.modules:
    logger_module = types.ModuleType("app.util.logger")
    logger_module.logger = Mock()
    sys.modules["app.util.logger"] = logger_module

from app.services.functions.function_manager import FunctionManager
from app.services.llm.openai_service import OpenAIService


class OpenAIServiceReasoningTests(unittest.IsolatedAsyncioTestCase):
    def build_service(self, config=None):
        return OpenAIService(
            config=config or {},
            api_key="test-key",
            function_manager=FunctionManager([]),
            system="Prueba",
        )

    async def test_luna_responses_uses_high_reasoning_by_default(self):
        service = self.build_service()
        service._create_response_with_local_retry = AsyncMock(
            return_value=SimpleNamespace(output=[], output_text="Hola")
        )

        result = [part async for part in service.generate_response("Hola")]

        self.assertEqual(result, ["Hola"])
        kwargs = service._create_response_with_local_retry.await_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(kwargs["reasoning"], {"effort": "high"})
        self.assertFalse(kwargs["store"])
        self.assertEqual(kwargs["include"], ["reasoning.encrypted_content"])
        self.assertNotIn("temperature", kwargs)

    async def test_environment_can_change_responses_reasoning(self):
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "medium"}):
            service = self.build_service({"reasoning_effort": "low"})
            service._create_response_with_local_retry = AsyncMock(
                return_value=SimpleNamespace(output=[], output_text="Listo")
            )

            _ = [part async for part in service.generate_response("Hola")]

        kwargs = service._create_response_with_local_retry.await_args.kwargs
        self.assertEqual(kwargs["reasoning"], {"effort": "medium"})

    async def test_responses_executes_function_and_submits_output(self):
        async def lookup(topic: str):
            """Busca información.

            topic (string): Tema que debe buscarse.
            """
            return f"resultado:{topic}"

        service = OpenAIService(
            config={},
            api_key="test-key",
            function_manager=FunctionManager([lookup]),
            system="Prueba",
        )
        function_call = {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": '{"topic":"baches"}',
            "status": "completed",
        }
        service._create_response_with_local_retry = AsyncMock(
            side_effect=[
                SimpleNamespace(output=[function_call], output_text=""),
                SimpleNamespace(output=[], output_text="Información encontrada"),
            ]
        )

        result = [part async for part in service.generate_response("Consulta")]

        self.assertEqual(result, ["Información encontrada"])
        second_input = service._create_response_with_local_retry.await_args_list[1].kwargs["input"]
        self.assertIn(function_call, second_input)
        self.assertIn(
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "resultado:baches",
            },
            second_input,
        )

    async def test_context_summary_uses_responses_without_tools(self):
        service = self.build_service()
        service.add_to_conversation("user", "Necesito reportar un bache")
        service._create_response_with_local_retry = AsyncMock(
            return_value=SimpleNamespace(
                output=[],
                output_text="El ciudadano reporta un bache.",
            )
        )

        await service.summarize_conversation_history()

        kwargs = service._create_response_with_local_retry.await_args.kwargs
        self.assertEqual(kwargs["reasoning"], {"effort": "low"})
        self.assertFalse(kwargs["store"])
        self.assertNotIn("tools", kwargs)
        self.assertEqual(
            service.conversation_history[-1],
            {
                "role": "system",
                "content": (
                    "Resumen de la conversación anterior: "
                    "El ciudadano reporta un bache."
                ),
            },
        )

    def test_function_schema_is_converted_for_responses(self):
        async def lookup(topic: str):
            """Busca información.

            topic (string): Tema que debe buscarse.
            """

        service = OpenAIService(
            config={},
            api_key="test-key",
            function_manager=FunctionManager([lookup]),
            system="Prueba",
        )

        self.assertEqual(
            service._responses_tools_payload()[0],
            {
                "type": "function",
                "name": "lookup",
                "description": "Busca información.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Tema que debe buscarse.",
                        }
                    },
                    "required": ["topic"],
                },
                "strict": False,
            },
        )

    def test_invalid_reasoning_value_falls_back_to_high(self):
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "turbo"}):
            service = self.build_service()
            self.assertEqual(service._reasoning_effort(), "high")


if __name__ == "__main__":
    unittest.main()
