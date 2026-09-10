import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
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

    def test_rotated_log_files_remain_visible_to_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "sam.log"
            Path(f"{log_path}.1").write_text(
                "2026-09-08 - ERROR - [OPENAI REQUEST FAILURE] APITimeoutError\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "2026-09-08 - INFO - servicio activo\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "LOG_TO_FILE": "true",
                    "LOG_FILE": str(log_path),
                    "LOG_FILE_BACKUP_COUNT": "1",
                },
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["openai_timeout"], 1)

    def test_report_payload_validation_block_is_visible(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(
                "2026-09-09 - WARNING - [REPORT PAYLOAD BLOCK] "
                "explicación vacía\n"
            )
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["report_payload_validation"], 1)

    def test_phone_filter_keeps_matching_lines_beyond_global_sample(self):
        phone = "5218114855841"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(
                f"2026-09-09 - WARNING - [REPORT PAYLOAD BLOCK] phone={phone} explicación vacía\n"
            )
            for index in range(4100):
                handle.write(f"2026-09-09 - DEBUG - unrelated line {index}\n")
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals(phone_number=phone)

        self.assertEqual(len(signals["phone_lines"]), 1)
        self.assertIn(phone, signals["phone_lines"][0])

    def test_ciac_timeout_is_attributed_to_ciac(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(
                "2026-09-09 - WARNING - [CIAC TIMEOUT] "
                "phone=5218114855841 type=ConnectTimeout\n"
            )
            handle.flush()
            with patch.dict(
                os.environ,
                {"LOG_TO_FILE": "true", "LOG_FILE": handle.name},
                clear=False,
            ):
                signals = _read_recent_log_signals()

        self.assertEqual(signals["counts"]["ciac_failure"], 1)
        self.assertEqual(signals["counts"]["network_timeout_unattributed"], 0)


if __name__ == "__main__":
    unittest.main()
