from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - production installs psycopg2
    psycopg2 = None
    Json = None

from app.services.conversation_control import normalize_phone_key
from app.util.logger import logger


PENDING_EVALUATION_REPORTS_TABLE = "conversation_evaluation_pending_reports"
_memory_events: dict[str, dict[str, dict[str, Any]]] = {}
_memory_lock = threading.RLock()
_schema_lock = threading.Lock()
_schema_ready = False


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


def ensure_pending_evaluation_report_storage(storage) -> bool:
    """Create the durable inbox used while a conclusion survey is active."""

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
                    CREATE TABLE IF NOT EXISTS {PENDING_EVALUATION_REPORTS_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        phone_number TEXT NOT NULL,
                        evaluation_folio TEXT NOT NULL,
                        event_key TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        query_params JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL,
                        UNIQUE (phone_number, event_key)
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS
                        idx_{PENDING_EVALUATION_REPORTS_TABLE}_phone_created
                    ON {PENDING_EVALUATION_REPORTS_TABLE}
                        (phone_number, created_at, id)
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception(
                "No se pudo preparar la cola de reportes pausados: %s",
                error,
            )
            return False
        finally:
            if conn is not None:
                conn.close()


def build_pending_evaluation_event_key(payload: dict[str, Any]) -> str:
    """Build an idempotent identity for one citizen event."""

    message_id = payload.get("message_id")
    if message_id not in (None, ""):
        return str(message_id)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def stage_pending_evaluation_report(
    storage,
    phone_number: str,
    *,
    evaluation_folio: str,
    payload: dict[str, Any],
    query_params: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Persist a citizen report turn without consuming it as survey feedback."""

    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    event_key = build_pending_evaluation_event_key(payload)
    stored_payload = {
        field: value
        for field, value in dict(payload).items()
        if field not in {"_sam_webhook_job_id"}
    }
    record = {
        "phone_number": key,
        "evaluation_folio": str(evaluation_folio or "").strip(),
        "event_key": event_key,
        "payload": stored_payload,
        "query_params": dict(query_params or {}),
        "created_at": timestamp,
        "updated_at": timestamp,
        "durable": False,
    }
    if not record["evaluation_folio"]:
        raise ValueError("evaluation_folio es obligatorio")

    with _memory_lock:
        phone_events = _memory_events.setdefault(key, {})
        phone_events.setdefault(event_key, record.copy())

    if not ensure_pending_evaluation_report_storage(storage):
        return record

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {PENDING_EVALUATION_REPORTS_TABLE}
                    (phone_number, evaluation_folio, event_key, payload,
                     query_params, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone_number, event_key) DO UPDATE SET
                    evaluation_folio = EXCLUDED.evaluation_folio,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    key,
                    record["evaluation_folio"],
                    event_key,
                    Json(stored_payload),
                    Json(record["query_params"]),
                    timestamp,
                    timestamp,
                ),
            )
        conn.commit()
        record["durable"] = True
        with _memory_lock:
            _memory_events.setdefault(key, {})[event_key] = record.copy()
    except Exception as error:
        logger.exception(
            "No se pudo pausar el reporte %s para %s: %s",
            event_key,
            key,
            error,
        )
    finally:
        if conn is not None:
            conn.close()
    return record


def get_pending_evaluation_reports(
    storage,
    phone_number: str,
) -> list[dict[str, Any]]:
    """Return paused report turns in their original arrival order."""

    key = normalize_phone_key(phone_number)
    database_was_queried = False
    if ensure_pending_evaluation_report_storage(storage):
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, phone_number, evaluation_folio, event_key,
                           payload, query_params, created_at, updated_at
                    FROM {PENDING_EVALUATION_REPORTS_TABLE}
                    WHERE phone_number = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (key,),
                )
                rows = cursor.fetchall()
            database_was_queried = True
            records = [
                {
                    "id": row[0],
                    "phone_number": str(row[1]),
                    "evaluation_folio": str(row[2]),
                    "event_key": str(row[3]),
                    "payload": dict(row[4] or {}),
                    "query_params": dict(row[5] or {}),
                    "created_at": float(row[6]),
                    "updated_at": float(row[7]),
                    "durable": True,
                }
                for row in rows
            ]
            with _memory_lock:
                if records:
                    _memory_events[key] = {
                        record["event_key"]: record.copy() for record in records
                    }
                else:
                    _memory_events.pop(key, None)
            return records
        except Exception as error:
            logger.exception(
                "No se pudieron consultar reportes pausados para %s: %s",
                key,
                error,
            )
        finally:
            if conn is not None:
                conn.close()

    if database_was_queried:
        return []
    with _memory_lock:
        return sorted(
            (record.copy() for record in _memory_events.get(key, {}).values()),
            key=lambda record: (record.get("created_at", 0), record["event_key"]),
        )


def list_resumable_pending_report_phones(
    storage,
    *,
    limit: int = 100,
) -> list[str]:
    """Find paused reports whose evaluation is no longer active.

    This is the recovery fence for a process restart after the evaluation was
    cleared but before its report turns could be returned to the webhook queue.
    """

    if not ensure_pending_evaluation_report_storage(storage):
        return []
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT pending.phone_number, MIN(pending.created_at) AS first_seen
                FROM {PENDING_EVALUATION_REPORTS_TABLE} AS pending
                LEFT JOIN conversation_evaluation_state AS evaluation
                  ON evaluation.phone_number = pending.phone_number
                WHERE evaluation.phone_number IS NULL
                GROUP BY pending.phone_number
                ORDER BY first_seen ASC
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            return [str(row[0]) for row in cursor.fetchall()]
    except Exception as error:
        logger.exception(
            "No se pudieron localizar reportes listos para reanudarse: %s",
            error,
        )
        return []
    finally:
        if conn is not None:
            conn.close()


def delete_pending_evaluation_report(
    storage,
    phone_number: str,
    event_key: str,
) -> bool:
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        phone_events = _memory_events.get(key, {})
        removed = phone_events.pop(str(event_key), None) is not None
        if not phone_events:
            _memory_events.pop(key, None)

    if not ensure_pending_evaluation_report_storage(storage):
        return removed
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM {PENDING_EVALUATION_REPORTS_TABLE}
                WHERE phone_number = %s AND event_key = %s
                """,
                (key, str(event_key)),
            )
            removed = cursor.rowcount > 0 or removed
        conn.commit()
    except Exception as error:
        logger.exception(
            "No se pudo eliminar reporte pausado %s para %s: %s",
            event_key,
            key,
            error,
        )
    finally:
        if conn is not None:
            conn.close()
    return removed


def clear_pending_evaluation_reports(storage, phone_number: str) -> bool:
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        removed = _memory_events.pop(key, None) is not None

    if not ensure_pending_evaluation_report_storage(storage):
        return removed
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {PENDING_EVALUATION_REPORTS_TABLE} "
                "WHERE phone_number = %s",
                (key,),
            )
            removed = cursor.rowcount > 0 or removed
        conn.commit()
    except Exception as error:
        logger.exception(
            "No se pudieron limpiar reportes pausados para %s: %s",
            key,
            error,
        )
    finally:
        if conn is not None:
            conn.close()
    return removed


def build_resumed_report_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh webhook identity while preserving citizen evidence."""

    payload = dict(record.get("payload") or {})
    event_key = str(record.get("event_key") or "unknown")
    replay_identity = f"{record.get('phone_number') or 'unknown'}:{event_key}"
    replay_hash = hashlib.sha256(replay_identity.encode()).hexdigest()[:24]
    original_message_id = payload.get("message_id")
    replay_message_id = f"evaluation-resume-{replay_hash}"
    payload["message_id"] = replay_message_id
    payload["request_id"] = replay_message_id
    payload["_sam_resumed_after_evaluation"] = True
    payload["_sam_original_message_id"] = original_message_id
    payload.pop("_sam_webhook_received_at", None)
    payload.pop("_sam_webhook_job_id", None)
    # The replay is a new internal turn. Keeping the old provider timestamp
    # would make the ordinary stale-event fence discard a report that waited
    # legitimately for the survey to finish.
    payload.pop("event_time", None)
    return payload
