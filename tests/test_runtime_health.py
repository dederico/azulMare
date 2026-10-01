import unittest
from unittest.mock import Mock, patch

from app.services.runtime_health import collect_runtime_health


class RuntimeHealthTests(unittest.TestCase):
    def test_health_probe_does_not_sleep_for_cpu_sample_and_bounds_ping(self):
        storage = Mock()
        storage.GetAll.return_value = []
        storage_factory = Mock(return_value=storage)

        psutil_module = Mock()
        psutil_module.sensors_temperatures.return_value = {}
        psutil_module.cpu_percent.return_value = 12.5
        psutil_module.virtual_memory.return_value.percent = 34.0
        psutil_module.disk_usage.return_value.percent = 56.0
        ping_function = Mock(return_value=0.012)

        with patch.dict(
            "os.environ",
            {"HEALTH_PING_TIMEOUT_SECONDS": "0.25"},
            clear=False,
        ):
            metrics = collect_runtime_health(
                "abc123",
                storage_factory=storage_factory,
                config_model=object,
                psutil_module=psutil_module,
                ping_function=ping_function,
            )

        psutil_module.cpu_percent.assert_called_once_with(interval=None)
        self.assertTrue(ping_function.call_args_list)
        for call in ping_function.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 0.25)
        self.assertEqual(metrics["deployment_sha"], "abc123")
        self.assertEqual(metrics["processor"], 12.5)


if __name__ == "__main__":
    unittest.main()
