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
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
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
) -> dict[str, Any]:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    completion = {
        "phone_number": key,
        "folio": str(folio).strip(),
        "completed_at": timestamp,
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
                    (phone_number, folio, completed_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    folio = EXCLUDED.folio,
                    completed_at = EXCLUDED.completed_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (key, completion["folio"], timestamp, timestamp),
            )
        conn.commit()
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
                    SELECT phone_number, folio, completed_at
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
