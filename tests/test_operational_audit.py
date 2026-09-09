import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

database_stub = types.ModuleType("app.util.database")
database_stub.LocalStorage = object
with patch.dict(sys.modules, {"app.util.database": database_stub}):
    from app.services.monitoring.operational_audit import _read_recent_log_signals


class OperationalAuditSignalTests(unittest.TestCase):
    def test_generic_connect_timeout_is_not_mislabeled_as_openai(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write("2026-09-08 - DEBUG - connect_tcp.failed exception=ConnectTimeout()\n")
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["openai_timeout"], 0)
        self.assertEqual(signals["counts"]["network_timeout_unattributed"], 1)

    def test_explicit_provider_timeouts_are_separated(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write("2026-09-08 - ERROR - [OPENAI REQUEST FAILURE] APITimeoutError\n")
            handle.write("2026-09-08 - ERROR - [CHAT2DESK TIMEOUT] Net::ReadTimeout\n")
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["openai_timeout"], 1)
        self.assertEqual(signals["counts"]["chat2desk_timeout"], 1)
        self.assertEqual(signals["counts"]["network_timeout_unattributed"], 0)

    def test_widget_empty_response_recovery_is_visible(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(
                "2026-09-08 - WARNING - [WIDGET EMPTY RESPONSE] "
                "Responses terminó sin texto\n"
            )
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["widget_empty_response"], 1)


if __name__ == "__main__":
    unittest.main()
