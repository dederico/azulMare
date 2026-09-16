import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx


def load_transfer_module():
    module_names = (
        "app.util.database",
        "app.models.Config",
        "app.models.Message",
        "app.util.logger",
    )
    previous = {name: sys.modules.get(name) for name in module_names}

    database_module = types.ModuleType("app.util.database")

    class LocalStorage:
        def Search(self, *args, **kwargs):
            return None

    database_module.LocalStorage = LocalStorage

    config_module = types.ModuleType("app.models.Config")
    config_module.Config = lambda **kwargs: types.SimpleNamespace(**kwargs)
    message_module = types.ModuleType("app.models.Message")
    message_module.Message = lambda **kwargs: types.SimpleNamespace(**kwargs)
    logger_module = types.ModuleType("app.util.logger")
    logger_module.logger = Mock()

    sys.modules.update(
        {
            "app.util.database": database_module,
            "app.models.Config": config_module,
            "app.models.Message": message_module,
            "app.util.logger": logger_module,
        }
    )
    try:
        path = (
            Path(__file__).parents[1]
            / "app/services/functions/implementations/transfer_message_event.py"
        )
        spec = importlib.util.spec_from_file_location("transfer_message_event_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class TimeoutClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, *args, **kwargs):
        raise httpx.ReadTimeout("Chat2Desk tardó demasiado")


class TransferMessageEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_timeout_is_reported_as_pending_not_failed(self):
        module = load_transfer_module()

        with (
            patch.dict(os.environ, {"CHAT2DESK_API_TOKEN": "test-token"}),
            patch.object(module.httpx, "AsyncClient", TimeoutClient),
        ):
            result = await module.transfer_to_group(970000001)

        self.assertTrue(result.startswith("TRANSFER_PENDING:"))
        self.assertNotIn("Error al transferir conversación", result)


if __name__ == "__main__":
    unittest.main()
