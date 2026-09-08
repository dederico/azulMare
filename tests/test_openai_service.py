import os
import sys
import types
import unittest
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

    async def test_luna_uses_high_reasoning_by_default(self):
        service = self.build_service()
        service._create_chat_completion_with_local_retry = AsyncMock(
            return_value="generator"
        )

        result = await service.llm_generator()

        self.assertEqual(result, "generator")
        kwargs = service._create_chat_completion_with_local_retry.await_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(kwargs["reasoning_effort"], "high")
        self.assertNotIn("temperature", kwargs)

    async def test_environment_can_lower_reasoning_without_code_change(self):
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "medium"}):
            service = self.build_service({"reasoning_effort": "low"})
            service._create_chat_completion_with_local_retry = AsyncMock(
                return_value="generator"
            )

            await service.llm_generator()

        kwargs = service._create_chat_completion_with_local_retry.await_args.kwargs
        self.assertEqual(kwargs["reasoning_effort"], "medium")

    def test_invalid_reasoning_value_falls_back_to_high(self):
        with patch.dict(os.environ, {"OPENAI_REASONING_EFFORT": "turbo"}):
            service = self.build_service()
            self.assertEqual(service._reasoning_effort(), "high")


if __name__ == "__main__":
    unittest.main()
