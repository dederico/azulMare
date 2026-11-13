import threading
import time
from typing import Any

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None

from app.services.conversation_control import normalize_phone_key
from app.util.logger import logger


EVALUATION_STATE_TABLE = "conversation_evaluation_state"
_memory_states: dict[str, dict[str, Any]] = {}
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


def ensure_evaluation_state_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {EVALUATION_STATE_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        folio TEXT NOT NULL,
                        client_id BIGINT,
                        channel_id BIGINT,
                        transport TEXT NOT NULL DEFAULT 'wa_direct',
                        visible_prompt TEXT,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {EVALUATION_STATE_TABLE}
                    ADD COLUMN IF NOT EXISTS visible_prompt TEXT
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.error("No se pudo preparar estado durable de evaluación: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def save_evaluation_state(
    storage,
    phone_number: str,
    *,
    state: str,
    folio: str,
    client_id=None,
    channel_id=None,
    transport: str = "wa_direct",
    visible_prompt: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    record = {
        "phone_number": key,
        "state": str(state or "").strip(),
        "folio": str(folio or "").strip(),
        "client_id": None if client_id in (None, "") else int(client_id),
        "channel_id": None if channel_id in (None, "") else int(channel_id),
        "transport": str(transport or "wa_direct"),
        "visible_prompt": str(visible_prompt or "").strip() or None,
        "updated_at": timestamp,
    }
    if not record["state"] or not record["folio"]:
        raise ValueError("state y folio son obligatorios para guardar una evaluación")

    with _memory_lock:
        _memory_states[key] = record.copy()

    if not ensure_evaluation_state_storage(storage):
        return record

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {EVALUATION_STATE_TABLE}
                    (phone_number, state, folio, client_id, channel_id, transport,
                     visible_prompt, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    state = EXCLUDED.state,
                    folio = EXCLUDED.folio,
                    client_id = EXCLUDED.client_id,
                    channel_id = EXCLUDED.channel_id,
                    transport = EXCLUDED.transport,
                    visible_prompt = EXCLUDED.visible_prompt,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    key,
                    record["state"],
                    record["folio"],
                    record["client_id"],
                    record["channel_id"],
                    record["transport"],
                    record["visible_prompt"],
                    timestamp,
                ),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo persistir evaluación para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()
    return record


def get_evaluation_state(
    storage,
    phone_number: str,
    *,
    max_age_seconds: float = 7 * 24 * 60 * 60,
    now: float | None = None,
) -> dict[str, Any] | None:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    cutoff = timestamp - float(max_age_seconds)

    database_was_queried = False
    if ensure_evaluation_state_storage(storage):
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT phone_number, state, folio, client_id, channel_id,
                           transport, visible_prompt, updated_at
                    FROM {EVALUATION_STATE_TABLE}
                    WHERE phone_number = %s AND updated_at >= %s
                    """,
                    (key, cutoff),
                )
                row = cursor.fetchone()
            database_was_queried = True
            if row:
                record = {
                    "phone_number": str(row[0]),
                    "state": str(row[1]),
                    "folio": str(row[2]),
                    "client_id": row[3],
                    "channel_id": row[4],
                    "transport": str(row[5] or "wa_direct"),
                    "visible_prompt": str(row[6] or "").strip() or None,
                    "updated_at": float(row[7]),
                }
                with _memory_lock:
                    _memory_states[key] = record.copy()
                return record
        except Exception as error:
            logger.error("No se pudo consultar evaluación para %s: %s", key, error)
        finally:
            if conn is not None:
                conn.close()

    # Cuando PostgreSQL respondió correctamente, su ausencia de fila es
    # autoritativa. No revivir un estado viejo que sobreviva en la memoria de
    # otra réplica después de completar o reiniciar la encuesta.
    if database_was_queried:
        with _memory_lock:
            _memory_states.pop(key, None)
        return None

    with _memory_lock:
        record = _memory_states.get(key)
        if record and float(record.get("updated_at") or 0) >= cutoff:
            return record.copy()
    return None


def migrate_legacy_evaluation_state(
    storage,
    legacy_phone_number: str,
    conversation_key: str,
    *,
    channel_id,
    transport: str,
    max_age_seconds: float = 7 * 24 * 60 * 60,
    now: float | None = None,
) -> bool:
    """Adopt a pre-scope WhatsApp evaluation without crossing channels."""

    legacy_key = normalize_phone_key(legacy_phone_number)
    scoped_key = normalize_phone_key(conversation_key)
    expected_transport = str(transport or "").strip().casefold()
    if (
        not legacy_key
        or legacy_key == scoped_key
        or channel_id in (None, "")
        or expected_transport not in {"whatsapp", "wa_direct", "wa_business"}
    ):
        return False

    timestamp = float(now if now is not None else time.time())
    cutoff = timestamp - float(max_age_seconds)
    if ensure_evaluation_state_storage(storage):
        conn = None
        try:
            conn = _connect(storage)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {EVALUATION_STATE_TABLE}
                        (phone_number, state, folio, client_id, channel_id,
                         transport, visible_prompt, updated_at)
                    SELECT %s, state, folio, client_id, channel_id, transport,
                           visible_prompt, updated_at
                    FROM {EVALUATION_STATE_TABLE}
                    WHERE phone_number = %s
                      AND channel_id = %s
                      AND LOWER(transport) IN ('whatsapp', 'wa_direct', 'wa_business')
                      AND updated_at >= %s
                    ON CONFLICT (phone_number) DO NOTHING
                    RETURNING phone_number
                    """,
                    (scoped_key, legacy_key, int(channel_id), cutoff),
                )
                inserted = bool(cursor.fetchone())
                cursor.execute(
                    f"""
                    DELETE FROM {EVALUATION_STATE_TABLE}
                    WHERE phone_number = %s
                      AND channel_id = %s
                      AND LOWER(transport)
                          IN ('whatsapp', 'wa_direct', 'wa_business')
                      AND EXISTS (
                          SELECT 1 FROM {EVALUATION_STATE_TABLE}
                          WHERE phone_number = %s
                      )
                    """,
                    (legacy_key, int(channel_id), scoped_key),
                )
            conn.commit()
            return inserted
        except Exception as error:
            logger.error(
                "No se pudo migrar evaluación legacy %s a %s: %s",
                legacy_key,
                scoped_key,
                error,
            )
            return False
        finally:
            if conn is not None:
                conn.close()

    with _memory_lock:
        legacy = _memory_states.get(legacy_key)
        legacy_matches = bool(
            legacy
            and int(legacy.get("channel_id") or 0) == int(channel_id)
            and str(legacy.get("transport") or "").strip().casefold()
            in {"whatsapp", "wa_direct", "wa_business"}
        )
        if scoped_key in _memory_states:
            if legacy_matches:
                _memory_states.pop(legacy_key, None)
            return False
        if (
            not legacy_matches
            or float(legacy.get("updated_at") or 0) < cutoff
        ):
            return False
        migrated = legacy.copy()
        migrated["phone_number"] = scoped_key
        _memory_states[scoped_key] = migrated
        _memory_states.pop(legacy_key, None)
        return True


def clear_evaluation_state(storage, phone_number: str) -> bool:
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        removed = _memory_states.pop(key, None) is not None

    if not ensure_evaluation_state_storage(storage):
        return removed

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {EVALUATION_STATE_TABLE} WHERE phone_number = %s",
                (key,),
            )
            removed = cursor.rowcount > 0 or removed
        conn.commit()
    except Exception as error:
        logger.error("No se pudo limpiar evaluación para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()
    return removed
