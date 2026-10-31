"""Durable, reversible routing between the primary and temporary WhatsApp channels.

The failover is intentionally opt-in.  When disabled every helper is a no-op and
the existing Chat2Desk routing remains unchanged.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - production installs psycopg2
    psycopg2 = None
    Json = None

from app.util.logger import logger


ROUTES_TABLE = "whatsapp_failover_routes"
PENDING_TABLE = "whatsapp_failover_pending_messages"
DEFAULT_ACTIVE_TTL_SECONDS = 23 * 60 * 60

_schema_lock = threading.Lock()
_schema_ready = False
_memory_lock = threading.RLock()
_memory_routes: dict[str, dict[str, Any]] = {}
_memory_pending: dict[tuple[str, str], dict[str, Any]] = {}


@dataclass(frozen=True)
class WhatsAppFailoverConfig:
    enabled: bool
    primary_channel_id: int
    failover_channel_id: int
    template_name: str
    template_language: str
    active_ttl_seconds: int = DEFAULT_ACTIVE_TTL_SECONDS
    allowed_phone_numbers: frozenset[str] = frozenset()


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def normalize_failover_phone(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _phone_allowlist(value: Any) -> frozenset[str]:
    return frozenset(
        phone
        for item in str(value or "").split(",")
        if (phone := normalize_failover_phone(item))
    )


def load_whatsapp_failover_config(
    environ: Mapping[str, str] | None = None,
) -> WhatsAppFailoverConfig:
    env = os.environ if environ is None else environ
    return WhatsAppFailoverConfig(
        enabled=_as_bool(env.get("WHATSAPP_FAILOVER_ENABLED", "false")),
        primary_channel_id=_as_int(
            env.get("WHATSAPP_PRIMARY_CHANNEL_ID"),
            43906,
        ),
        failover_channel_id=_as_int(
            env.get("WHATSAPP_FAILOVER_CHANNEL_ID"),
            43943,
        ),
        template_name=(
            str(env.get("WHATSAPP_FAILOVER_TEMPLATE") or "continuidad_canal_temporal")
            .strip()
        ),
        template_language=(
            str(env.get("WHATSAPP_FAILOVER_TEMPLATE_LANGUAGE") or "es_mx")
            .strip()
        ),
        active_ttl_seconds=max(
            60,
            _as_int(
                env.get("WHATSAPP_FAILOVER_ACTIVE_TTL_SECONDS"),
                DEFAULT_ACTIVE_TTL_SECONDS,
            ),
        ),
        allowed_phone_numbers=_phone_allowlist(
            env.get("WHATSAPP_FAILOVER_ALLOWED_PHONES", "")
        ),
    )


def is_phone_allowed_for_failover(
    phone_number: Any,
    config: WhatsAppFailoverConfig,
) -> bool:
    return (
        not config.allowed_phone_numbers
        or normalize_failover_phone(phone_number) in config.allowed_phone_numbers
    )


def is_failover_candidate(
    *,
    config: WhatsAppFailoverConfig,
    message_type: str,
    transport: str,
    channel_id: Any,
    replay: bool = False,
) -> bool:
    if not config.enabled or replay:
        return False
    if str(message_type or "").strip().casefold() != "from_client":
        return False
    if str(transport or "wa_direct").strip().casefold() != "wa_direct":
        return False
    try:
        normalized_channel_id = int(channel_id)
    except (TypeError, ValueError):
        return False
    return normalized_channel_id in {
        config.primary_channel_id,
        config.failover_channel_id,
    }


def build_failover_hsm_text(config: WhatsAppFailoverConfig) -> str:
    """Build Chat2Desk's HSM command for a template without variables."""
    return f"@HSM@\n{config.template_name}|{config.template_language}"


def build_failover_replay_payload(
    payload: Mapping[str, Any],
    *,
    failover_client_id: Any,
    failover_channel_id: int,
) -> dict[str, Any]:
    replay = copy.deepcopy(dict(payload))
    original_message_id = str(
        replay.get("message_id")
        or replay.get("request_id")
        or f"unknown-{time.time_ns()}"
    )
    replay["message_id"] = f"{original_message_id}:sam-failover"
    replay["client_id"] = failover_client_id
    replay["channel_id"] = failover_channel_id
    replay["transport"] = "wa_direct"
    replay["_sam_failover_replay"] = True
    replay["_sam_failover_original_message_id"] = original_message_id
    replay["_sam_failover_original_event_time"] = replay.get("event_time")
    # The citizen may confirm the temporary channel much later than the
    # original event. Treat the durable replay as freshly received while
    # retaining the provider timestamp above for audit purposes.
    replay["event_time"] = datetime.now(timezone.utc).isoformat()
    replay.pop("_sam_webhook_job_id", None)
    return replay


def _connect(storage):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 no está instalado")
    return psycopg2.connect(
        dbname=storage.dbName,
        user=storage.user,
        password=storage.password,
        host=storage.host,
        port=storage.port,
    )


def ensure_whatsapp_failover_storage(storage) -> bool:
    global _schema_ready
    if storage is None or psycopg2 is None:
        return False
    if _schema_ready:
        return True
    with _schema_lock:
        if _schema_ready:
            return True
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ROUTES_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        primary_client_id TEXT,
                        failover_client_id TEXT,
                        primary_channel_id BIGINT NOT NULL,
                        failover_channel_id BIGINT NOT NULL,
                        hsm_sent_at DOUBLE PRECISION,
                        activated_at DOUBLE PRECISION,
                        expires_at DOUBLE PRECISION,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {PENDING_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        phone_number TEXT NOT NULL,
                        original_message_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL,
                        UNIQUE (phone_number, original_message_id)
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{PENDING_TABLE}_ready
                    ON {PENDING_TABLE} (phone_number, status, id)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{ROUTES_TABLE}_clients
                    ON {ROUTES_TABLE} (primary_client_id, failover_client_id, status)
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception("No se pudo preparar el failover de WhatsApp: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def _use_memory_or_require_durable_storage(storage) -> bool:
    if storage is None:
        return True
    if not ensure_whatsapp_failover_storage(storage):
        raise RuntimeError("almacenamiento durable de failover no disponible")
    return False


def _message_id(payload: Mapping[str, Any]) -> str:
    return str(
        payload.get("message_id")
        or payload.get("request_id")
        or f"generated-{time.time_ns()}"
    )


def stage_primary_inbound(
    storage,
    *,
    phone_number: str,
    primary_client_id: Any,
    payload: Mapping[str, Any],
    config: WhatsAppFailoverConfig,
) -> dict[str, Any]:
    """Persist an original inbound and decide whether an HSM is required."""
    phone = str(phone_number or "").strip()
    message_id = _message_id(payload)
    now = time.time()

    if _use_memory_or_require_durable_storage(storage):
        with _memory_lock:
            _memory_pending.setdefault(
                (phone, message_id),
                {
                    "phone_number": phone,
                    "original_message_id": message_id,
                    "payload": copy.deepcopy(dict(payload)),
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            route = _memory_routes.get(phone)
            if (
                route
                and route.get("status") == "active"
                and float(route.get("expires_at") or 0) > now
                and route.get("failover_client_id")
            ):
                return {
                    "action": "replay",
                    "failover_client_id": route["failover_client_id"],
                }
            if route and route.get("status") == "awaiting_confirmation":
                return {"action": "wait"}
            if route and route.get("status") == "hsm_sending":
                return {"action": "send_hsm"}
            _memory_routes[phone] = {
                "phone_number": phone,
                "status": "hsm_sending",
                "primary_client_id": str(primary_client_id or ""),
                "failover_client_id": None,
                "primary_channel_id": config.primary_channel_id,
                "failover_channel_id": config.failover_channel_id,
                "hsm_sent_at": None,
                "activated_at": None,
                "expires_at": None,
                "created_at": now,
                "updated_at": now,
            }
            return {"action": "send_hsm"}

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {PENDING_TABLE}
                    (phone_number, original_message_id, payload, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                ON CONFLICT (phone_number, original_message_id) DO NOTHING
                """,
                (phone, message_id, Json(dict(payload)), now, now),
            )
            cursor.execute(
                f"SELECT status, failover_client_id, expires_at FROM {ROUTES_TABLE} "
                "WHERE phone_number = %s FOR UPDATE",
                (phone,),
            )
            row = cursor.fetchone()
            if row and row[0] == "active" and float(row[2] or 0) > now and row[1]:
                result = {"action": "replay", "failover_client_id": row[1]}
            elif row and row[0] == "awaiting_confirmation":
                result = {"action": "wait"}
            elif row and row[0] == "hsm_sending":
                result = {"action": "send_hsm"}
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {ROUTES_TABLE}
                        (phone_number, status, primary_client_id, failover_client_id,
                         primary_channel_id, failover_channel_id, hsm_sent_at,
                         activated_at, expires_at, created_at, updated_at)
                    VALUES (%s, 'hsm_sending', %s, NULL, %s, %s, NULL,
                            NULL, NULL, %s, %s)
                    ON CONFLICT (phone_number) DO UPDATE SET
                        status = 'hsm_sending',
                        primary_client_id = EXCLUDED.primary_client_id,
                        failover_client_id = NULL,
                        primary_channel_id = EXCLUDED.primary_channel_id,
                        failover_channel_id = EXCLUDED.failover_channel_id,
                        hsm_sent_at = NULL,
                        activated_at = NULL,
                        expires_at = NULL,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        phone,
                        str(primary_client_id or ""),
                        config.primary_channel_id,
                        config.failover_channel_id,
                        now,
                        now,
                    ),
                )
                result = {"action": "send_hsm"}
        conn.commit()
        return result
    finally:
        if conn is not None:
            conn.close()


def mark_failover_hsm_result(
    storage,
    *,
    phone_number: str,
    success: bool,
) -> None:
    phone = str(phone_number or "").strip()
    now = time.time()
    status = "awaiting_confirmation" if success else "hsm_failed"
    if _use_memory_or_require_durable_storage(storage):
        with _memory_lock:
            route = _memory_routes.get(phone)
            if route:
                route.update(
                    status=status,
                    hsm_sent_at=now if success else None,
                    updated_at=now,
                )
        return
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {ROUTES_TABLE}
                SET status = %s,
                    hsm_sent_at = CASE WHEN %s THEN %s ELSE hsm_sent_at END,
                    updated_at = %s
                WHERE phone_number = %s
                """,
                (status, success, now, now, phone),
            )
        conn.commit()
    finally:
        if conn is not None:
            conn.close()


def activate_failover_and_list_pending(
    storage,
    *,
    phone_number: str,
    failover_client_id: Any,
    config: WhatsAppFailoverConfig,
) -> list[dict[str, Any]]:
    phone = str(phone_number or "").strip()
    now = time.time()
    expires_at = now + config.active_ttl_seconds
    if _use_memory_or_require_durable_storage(storage):
        with _memory_lock:
            route = _memory_routes.setdefault(
                phone,
                {
                    "phone_number": phone,
                    "created_at": now,
                    "primary_client_id": "",
                    "primary_channel_id": config.primary_channel_id,
                },
            )
            route.update(
                status="active",
                failover_client_id=str(failover_client_id or ""),
                failover_channel_id=config.failover_channel_id,
                activated_at=now,
                expires_at=expires_at,
                updated_at=now,
            )
            return [
                copy.deepcopy(row)
                for (row_phone, _), row in sorted(
                    _memory_pending.items(),
                    key=lambda item: item[1]["created_at"],
                )
                if row_phone == phone and row.get("status") == "pending"
            ]

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {ROUTES_TABLE}
                    (phone_number, status, primary_client_id, failover_client_id,
                     primary_channel_id, failover_channel_id, hsm_sent_at,
                     activated_at, expires_at, created_at, updated_at)
                VALUES (%s, 'active', NULL, %s, %s, %s, NULL, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    status = 'active',
                    failover_client_id = EXCLUDED.failover_client_id,
                    failover_channel_id = EXCLUDED.failover_channel_id,
                    activated_at = EXCLUDED.activated_at,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    phone,
                    str(failover_client_id or ""),
                    config.primary_channel_id,
                    config.failover_channel_id,
                    now,
                    expires_at,
                    now,
                    now,
                ),
            )
            cursor.execute(
                f"""
                SELECT id, original_message_id, payload
                FROM {PENDING_TABLE}
                WHERE phone_number = %s AND status = 'pending'
                ORDER BY id ASC
                """,
                (phone,),
            )
            rows = cursor.fetchall()
        conn.commit()
        return [
            {"id": row[0], "original_message_id": row[1], "payload": row[2]}
            for row in rows
        ]
    finally:
        if conn is not None:
            conn.close()


def list_pending_for_active_route(storage, *, phone_number: str) -> list[dict[str, Any]]:
    phone = str(phone_number or "").strip()
    if _use_memory_or_require_durable_storage(storage):
        with _memory_lock:
            return [
                copy.deepcopy(row)
                for (row_phone, _), row in sorted(
                    _memory_pending.items(),
                    key=lambda item: item[1]["created_at"],
                )
                if row_phone == phone and row.get("status") == "pending"
            ]
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, original_message_id, payload
                FROM {PENDING_TABLE}
                WHERE phone_number = %s AND status = 'pending'
                ORDER BY id ASC
                """,
                (phone,),
            )
            rows = cursor.fetchall()
        return [
            {"id": row[0], "original_message_id": row[1], "payload": row[2]}
            for row in rows
        ]
    finally:
        if conn is not None:
            conn.close()


def mark_pending_replayed(storage, *, phone_number: str, original_message_id: str) -> None:
    phone = str(phone_number or "").strip()
    message_id = str(original_message_id)
    now = time.time()
    if _use_memory_or_require_durable_storage(storage):
        with _memory_lock:
            row = _memory_pending.get((phone, message_id))
            if row:
                row.update(status="replayed", updated_at=now)
        return
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {PENDING_TABLE}
                SET status = 'replayed', updated_at = %s
                WHERE phone_number = %s AND original_message_id = %s
                """,
                (now, phone, message_id),
            )
        conn.commit()
    finally:
        if conn is not None:
            conn.close()


def resolve_failover_outbound(
    storage,
    *,
    client_id: Any,
    channel_id: Any,
    transport: str,
    phone_number: str | None = None,
    config: WhatsAppFailoverConfig | None = None,
) -> tuple[Any, Any]:
    """Return the active temporary client/channel, or the unchanged route."""
    config = config or load_whatsapp_failover_config()
    if not config.enabled or str(transport or "").casefold() != "wa_direct":
        return client_id, channel_id
    now = time.time()
    phone = str(phone_number or "").strip()
    client_key = str(client_id or "")

    if storage is None:
        with _memory_lock:
            candidates = (
                [_memory_routes.get(phone)]
                if phone
                else list(_memory_routes.values())
            )
            for route in candidates:
                if not route or route.get("status") != "active":
                    continue
                if float(route.get("expires_at") or 0) <= now:
                    continue
                if phone or client_key in {
                    str(route.get("primary_client_id") or ""),
                    str(route.get("failover_client_id") or ""),
                }:
                    return route.get("failover_client_id") or client_id, config.failover_channel_id
        return client_id, channel_id

    if not ensure_whatsapp_failover_storage(storage):
        return client_id, channel_id

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            if phone:
                cursor.execute(
                    f"""
                    SELECT failover_client_id, failover_channel_id
                    FROM {ROUTES_TABLE}
                    WHERE phone_number = %s AND status = 'active' AND expires_at > %s
                    """,
                    (phone, now),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT failover_client_id, failover_channel_id
                    FROM {ROUTES_TABLE}
                    WHERE status = 'active' AND expires_at > %s
                      AND (primary_client_id = %s OR failover_client_id = %s)
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (now, client_key, client_key),
                )
            row = cursor.fetchone()
        if row and row[0]:
            return row[0], int(row[1])
        return client_id, channel_id
    except Exception as error:
        logger.exception("No se pudo resolver la ruta temporal de WhatsApp: %s", error)
        return client_id, channel_id
    finally:
        if conn is not None:
            conn.close()
