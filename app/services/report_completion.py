import threading
import time
from typing import Any

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None

from app.services.conversation_control import normalize_phone_key
from app.util.logger import logger


REPORT_COMPLETION_TABLE = "conversation_report_completions"

_memory_completions: dict[str, dict[str, Any]] = {}
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


def ensure_report_completion_storage(storage) -> bool:
    global _schema_ready
    if psycopg2 is None:
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
                    CREATE TABLE IF NOT EXISTS {REPORT_COMPLETION_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        folio TEXT NOT NULL,
                        completed_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL,
                        notification_message TEXT,
                        request_id TEXT,
                        origin_uid TEXT,
                        origin_message_id TEXT,
                        client_id TEXT,
                        channel_id TEXT,
                        transport TEXT,
                        notified_at DOUBLE PRECISION
                    )
                    """
                )
                for column, definition in (
                    ("notification_message", "TEXT"),
                    ("request_id", "TEXT"),
                    ("origin_uid", "TEXT"),
                    ("origin_message_id", "TEXT"),
                    ("client_id", "TEXT"),
                    ("channel_id", "TEXT"),
                    ("transport", "TEXT"),
                    ("notified_at", "DOUBLE PRECISION"),
                ):
                    cursor.execute(
                        f"ALTER TABLE {REPORT_COMPLETION_TABLE} "
                        f"ADD COLUMN IF NOT EXISTS {column} {definition}"
                    )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.error("No se pudo preparar folio durable: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def record_report_completion(
    storage,
    phone_number: str,
    folio: str,
    *,
    now: float | None = None,
    notification_message: str | None = None,
    request_id: str | None = None,
    origin_uid: str | None = None,
    origin_message_id: str | None = None,
    client_id: str | int | None = None,
    channel_id: str | int | None = None,
    transport: str | None = None,
) -> dict[str, Any]:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    completion = {
        "phone_number": key,
        "folio": str(folio).strip(),
        "completed_at": timestamp,
        "notification_message": notification_message,
        "request_id": request_id,
        "origin_uid": origin_uid,
        "origin_message_id": origin_message_id,
        "client_id": None if client_id is None else str(client_id),
        "channel_id": None if channel_id is None else str(channel_id),
        "transport": transport,
        "notified_at": None,
        "durable": False,
    }
    with _memory_lock:
        _memory_completions[key] = completion.copy()

    if storage is None or not ensure_report_completion_storage(storage):
        return completion

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {REPORT_COMPLETION_TABLE}
                    (phone_number, folio, completed_at, updated_at,
                     notification_message, request_id, origin_uid,
                     origin_message_id, client_id, channel_id, transport,
                     notified_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                ON CONFLICT (phone_number) DO UPDATE SET
                    folio = EXCLUDED.folio,
                    completed_at = EXCLUDED.completed_at,
                    updated_at = EXCLUDED.updated_at,
                    notification_message = EXCLUDED.notification_message,
                    request_id = EXCLUDED.request_id,
                    origin_uid = EXCLUDED.origin_uid,
                    origin_message_id = EXCLUDED.origin_message_id,
                    client_id = EXCLUDED.client_id,
                    channel_id = EXCLUDED.channel_id,
                    transport = EXCLUDED.transport,
                    notified_at = NULL
                """,
                (
                    key, completion["folio"], timestamp, timestamp,
                    notification_message, request_id, origin_uid,
                    origin_message_id,
                    completion["client_id"], completion["channel_id"],
                    transport,
                ),
            )
        conn.commit()
        completion["durable"] = True
        with _memory_lock:
            _memory_completions[key] = completion.copy()
    except Exception as error:
        logger.error("No se pudo persistir folio para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()
    return completion


def get_recent_report_completion(
    storage,
    phone_number: str,
    *,
    max_age_seconds: float = 1800,
    now: float | None = None,
) -> dict[str, Any] | None:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    cutoff = timestamp - float(max_age_seconds)

    if storage is not None and ensure_report_completion_storage(storage):
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT phone_number, folio, completed_at,
                           notification_message, request_id, origin_uid,
                           origin_message_id, client_id, channel_id, transport,
                           notified_at
                    FROM {REPORT_COMPLETION_TABLE}
                    WHERE phone_number = %s AND completed_at >= %s
                    """,
                    (key, cutoff),
                )
                row = cursor.fetchone()
            if row:
                completion = {
                    "phone_number": str(row[0]),
                    "folio": str(row[1]),
                    "completed_at": float(row[2]),
                    "notification_message": row[3],
                    "request_id": row[4],
                    "origin_uid": row[5],
                    "origin_message_id": row[6],
                    "client_id": row[7],
                    "channel_id": row[8],
                    "transport": row[9],
                    "notified_at": row[10],
                    "durable": True,
                }
                with _memory_lock:
                    _memory_completions[key] = completion.copy()
                return completion
        except Exception as error:
            logger.error("No se pudo consultar folio reciente para %s: %s", key, error)
        finally:
            if conn is not None:
                conn.close()

    with _memory_lock:
        completion = _memory_completions.get(key)
        if completion and float(completion.get("completed_at") or 0) >= cutoff:
            return completion.copy()
    return None


def mark_report_completion_notified(
    storage,
    phone_number: str,
    *,
    now: float | None = None,
) -> bool:
    """Mark the latest confirmed folio as delivered to the citizen."""
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    with _memory_lock:
        completion = _memory_completions.get(key)
        if completion:
            completion["notified_at"] = timestamp

    if storage is None or not ensure_report_completion_storage(storage):
        return completion is not None
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {REPORT_COMPLETION_TABLE}
                SET notified_at = %s, updated_at = %s
                WHERE phone_number = %s
                """,
                (timestamp, timestamp, key),
            )
            changed = cursor.rowcount == 1
        conn.commit()
        return changed
    finally:
        if conn is not None:
            conn.close()


def is_delayed_pre_completion_event(
    completion: dict[str, Any] | None,
    event_timestamp: float | None,
    *,
    tolerance_seconds: float = 3.0,
) -> bool:
    """Only suppress clearly old webhooks, never new citizen replies after a folio."""
    if not completion or event_timestamp is None:
        return False
    completed_at = float(completion.get("completed_at") or 0)
    return bool(completed_at and event_timestamp < completed_at - tolerance_seconds)


def is_queued_before_completion(
    completion: dict[str, Any] | None,
    received_at: float | None,
) -> bool:
    """Return whether an inbound was already queued when CIAC confirmed a folio.

    ``received_at`` and ``completed_at`` are both server timestamps, so unlike
    the provider event timestamp they do not need a clock-skew tolerance.  The
    inbound that actually creates the report cannot match this condition: no
    completion exists yet when that job starts.  This fence is for a later job
    that waited in the durable queue while the previous turn created the folio.
    """
    if not completion or received_at is None:
        return False
    try:
        completed_at = float(completion.get("completed_at") or 0)
        queued_at = float(received_at)
    except (TypeError, ValueError, AttributeError):
        return False
    return bool(completed_at > 0 and queued_at < completed_at)


def clear_report_completion(storage, phone_number: str) -> bool:
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        removed = _memory_completions.pop(key, None) is not None

    if storage is None or not ensure_report_completion_storage(storage):
        return removed
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {REPORT_COMPLETION_TABLE} WHERE phone_number = %s",
                (key,),
            )
            removed = cursor.rowcount > 0 or removed
        conn.commit()
    except Exception as error:
        logger.error("No se pudo limpiar folio reciente para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()
    return removed
