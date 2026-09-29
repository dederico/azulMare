"""Resilient helpers for transient outbound HTTP failures."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx


DEFINITELY_PRE_SEND_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


async def post_json_with_retry(
    url: str,
    *,
    json: dict,
    headers: dict,
    attempts: int = 3,
    base_delay_seconds: float = 0.5,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> httpx.Response:
    """POST JSON and retry only failures known to happen before transmission.

    The caller still owns domain validation of a successful HTTP response.  A
    read/write timeout or an HTTP error is deliberately *not* retried here:
    the remote provider may already have accepted the non-idempotent POST.
    A terminal exception is re-raised so the durable webhook queue can retry
    the inbound event without silently advancing the dialogue.
    """

    if attempts < 1:
        raise ValueError("attempts debe ser mayor o igual a 1")
    client_factory = client_factory or httpx.AsyncClient

    last_error: Exception | None = None
    response: httpx.Response | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with client_factory(
                timeout=httpx.Timeout(20.0, connect=8.0)
            ) as client:
                response = await client.post(url, json=json, headers=headers)
            last_error = None
        except DEFINITELY_PRE_SEND_ERRORS as error:
            last_error = error
            response = None
        except httpx.TransportError:
            # Delivery is ambiguous once the connection was established.  An
            # immediate retry could send the same WhatsApp message twice.
            raise

        should_retry = (
            attempt < attempts
            and last_error is not None
        )
        if not should_retry:
            break
        await asyncio.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    if last_error is not None:
        raise last_error
    if response is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("No se obtuvo respuesta del servicio externo")
    return response
