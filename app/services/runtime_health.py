import json
import os
from typing import Any, Callable

import ping3
import psutil


DEFAULT_PING_DOMAINS = (
    {"name": "AWS", "domain": "ec2.amazonaws.com"},
    {"name": "Google", "domain": "google.com"},
    {"name": "Twilio", "domain": "chunderw-gll.twilio.com"},
)


def collect_runtime_health(
    deployment_sha: str,
    *,
    storage_factory: Callable[[], Any],
    config_model: Any,
    psutil_module: Any = psutil,
    ping_function: Callable[..., float | None] = ping3.ping,
) -> dict[str, Any]:
    """Collect blocking health probes from a worker thread, never the event loop."""
    storage = storage_factory()
    configs = {
        config.name: config.value
        for config in storage.GetAll(config_model)
    }

    configured_domains = []
    if configs.get("PingDomains"):
        try:
            configured_domains = json.loads(configs["PingDomains"])
        except (TypeError, ValueError, json.JSONDecodeError):
            configured_domains = []
    domains = [*configured_domains, *DEFAULT_PING_DOMAINS]
    ping_timeout = max(
        0.05,
        float(os.environ.get("HEALTH_PING_TIMEOUT_SECONDS", "0.5")),
    )

    try:
        temperatures = psutil_module.sensors_temperatures()
        temperature = temperatures["coretemp"][0].current if temperatures else False
    except (AttributeError, IndexError, KeyError):
        temperature = False

    pings = []
    for domain in domains:
        ping_seconds = ping_function(domain["domain"], timeout=ping_timeout)
        ping_milliseconds = (
            int(ping_seconds * 1000) if ping_seconds is not None else False
        )
        pings.append(
            {
                "domain": domain["domain"],
                "ping": ping_milliseconds,
                "name": domain["name"],
            }
        )

    return {
        "deployment_sha": deployment_sha,
        # interval=None is non-blocking; interval=1 slept for one second on the
        # same loop that serves widget and WhatsApp traffic.
        "processor": psutil_module.cpu_percent(interval=None),
        "memory": psutil_module.virtual_memory().percent,
        "storage": psutil_module.disk_usage("/").percent,
        "temperature": temperature,
        "ping": pings,
    }
