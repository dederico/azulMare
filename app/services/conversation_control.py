import re
import threading
import time
from typing import Any

try:
    import psycopg2
except ImportError:  # Permite el fallback en memoria en entornos sin PostgreSQL.
    psycopg2 = None

try:
    from app.util.logger import logger
except ImportError:  # Mantiene disponible el fallback en memoria en pruebas mínimas.
    import logging

    logger = logging.getLogger(__name__)


CONTROL_TABLE = "conversation_controls"
HUMAN_MODE = "human"
_memory_controls: dict[str, dict[str, Any]] = {}
_memory_lock = threading.RLock()
_schema_lock = threading.Lock()
_schema_ready = False


def normalize_phone_key(phone_number: str | None) -> str:
    digits = re.sub(r"\D", "", str(phone_number or ""))
    return digits or str(phone_number or "").strip()


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


def ensure_conversation_control_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {CONTROL_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        mode TEXT NOT NULL,
                        expires_at DOUBLE PRECISION,
                        source TEXT,
                        transfer_message_id TEXT,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.error("No se pudo preparar control persistente de conversación: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def activate_human_control(
    phone_number: str,
    *,
    expires_at: float | None,
    source: str,
    transfer_message_id: str | int | None = None,
    storage=None,
) -> dict[str, Any]:
    key = normalize_phone_key(phone_number)
    control = {
        "phone_number": key,
        "mode": HUMAN_MODE,
        "expires_at": float(expires_at) if expires_at is not None else None,
        "source": str(source or "unknown"),
        "transfer_message_id": str(transfer_message_id or ""),
        "updated_at": time.time(),
    }

    with _memory_lock:
        _memory_controls[key] = control.copy()

    if storage is None or not ensure_conversation_control_storage(storage):
        return control

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {CONTROL_TABLE}
                    (phone_number, mode, expires_at, source, transfer_message_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    expires_at = EXCLUDED.expires_at,
                    source = EXCLUDED.source,
                    transfer_message_id = EXCLUDED.transfer_message_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    control["phone_number"],
                    control["mode"],
                    control["expires_at"],
                    control["source"],
                    control["transfer_message_id"],
                    control["updated_at"],
                ),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo persistir takeover humano para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()

    return control


def release_human_control(phone_number: str, *, storage=None) -> None:
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        _memory_controls.pop(key, None)

    if storage is None or not ensure_conversation_control_storage(storage):
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {CONTROL_TABLE} WHERE phone_number = %s",
                (key,),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo liberar control humano persistente para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()


def get_active_human_control(phone_number: str, *, storage=None) -> dict[str, Any] | None:
    key = normalize_phone_key(phone_number)
    now = time.time()
    persisted = None
    persistent_storage_checked = False

    if storage is not None and ensure_conversation_control_storage(storage):
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT phone_number, mode, expires_at, source, transfer_message_id, updated_at
                    FROM {CONTROL_TABLE}
                    WHERE phone_number = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
            persistent_storage_checked = True
            if row:
                persisted = {
                    "phone_number": row[0],
                    "mode": row[1],
                    "expires_at": float(row[2]) if row[2] is not None else None,
                    "source": row[3],
                    "transfer_message_id": row[4],
                    "updated_at": float(row[5] or 0),
                }
        except Exception as error:
            logger.error("No se pudo consultar takeover persistente para %s: %s", key, error)
        finally:
            if conn is not None:
                conn.close()

    if persistent_storage_checked and persisted is None:
        # PostgreSQL is authoritative when it was queried successfully. This also
        # propagates releases made by another replica or by an audited DB cleanup.
        with _memory_lock:
            _memory_controls.pop(key, None)
        return None

    candidate = persisted
    if candidate is None:
        with _memory_lock:
            candidate = _memory_controls.get(key)
            candidate = candidate.copy() if candidate else None

    if not candidate or candidate.get("mode") != HUMAN_MODE:
        return None

    expires_at = candidate.get("expires_at")
    if expires_at is not None and float(expires_at) <= now:
        release_human_control(key, storage=storage)
        return None

    with _memory_lock:
        _memory_controls[key] = candidate.copy()
    return candidate
