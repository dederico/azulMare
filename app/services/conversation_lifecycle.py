import threading
import time
from typing import Any

try:
    import psycopg2
except ImportError:  # Permite pruebas y desarrollo sin PostgreSQL.
    psycopg2 = None

try:
    from app.util.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from app.services.conversation_control import normalize_phone_key


LIFECYCLE_TABLE = "conversation_lifecycle"

_memory_state: dict[str, dict[str, Any]] = {}
_memory_lock = threading.RLock()
_schema_lock = threading.Lock()
_schema_ready = False


def build_session_key(request_id=None, dialog_id=None) -> str:
    """Build a stable Chat2Desk session key even when is_new_request repeats."""
    if request_id not in (None, ""):
        return f"request:{request_id}"
    if dialog_id not in (None, ""):
        return f"dialog:{dialog_id}"
    return "unknown"


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


def ensure_conversation_lifecycle_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {LIFECYCLE_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        last_inbound_uid TEXT,
                        last_inbound_at DOUBLE PRECISION,
                        session_key TEXT,
                        greeted_session_key TEXT,
                        inactivity_claim_uid TEXT,
                        inactivity_closed_for_uid TEXT,
                        reopen_greeting_pending BOOLEAN NOT NULL DEFAULT FALSE,
                        client_id TEXT,
                        channel_id TEXT,
                        transport TEXT,
                        inactivity_failure_count INTEGER NOT NULL DEFAULT 0,
                        inactivity_next_retry_at DOUBLE PRECISION,
                        inactivity_terminal BOOLEAN NOT NULL DEFAULT FALSE,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {LIFECYCLE_TABLE}
                        ADD COLUMN IF NOT EXISTS client_id TEXT,
                        ADD COLUMN IF NOT EXISTS channel_id TEXT,
                        ADD COLUMN IF NOT EXISTS transport TEXT,
                        ADD COLUMN IF NOT EXISTS inactivity_failure_count INTEGER NOT NULL DEFAULT 0,
                        ADD COLUMN IF NOT EXISTS inactivity_next_retry_at DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS inactivity_terminal BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.error("No se pudo preparar lifecycle persistente: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def _blank_state(phone_number: str) -> dict[str, Any]:
    return {
        "phone_number": phone_number,
        "last_inbound_uid": None,
        "last_inbound_at": None,
        "session_key": None,
        "greeted_session_key": None,
        "inactivity_claim_uid": None,
        "inactivity_closed_for_uid": None,
        "reopen_greeting_pending": False,
        "client_id": None,
        "channel_id": None,
        "transport": None,
        "inactivity_failure_count": 0,
        "inactivity_next_retry_at": None,
        "inactivity_terminal": False,
        "updated_at": 0.0,
    }


def _row_to_state(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "phone_number": row[0],
        "last_inbound_uid": row[1],
        "last_inbound_at": float(row[2]) if row[2] is not None else None,
        "session_key": row[3],
        "greeted_session_key": row[4],
        "inactivity_claim_uid": row[5],
        "inactivity_closed_for_uid": row[6],
        "reopen_greeting_pending": bool(row[7]),
        "client_id": row[8],
        "channel_id": row[9],
        "transport": row[10],
        "inactivity_failure_count": int(row[11] or 0),
        "inactivity_next_retry_at": float(row[12]) if row[12] is not None else None,
        "inactivity_terminal": bool(row[13]),
        "updated_at": float(row[14] or 0),
    }


def _uid_is_at_least(candidate, current, candidate_at, current_at) -> bool:
    if current in (None, ""):
        return True
    try:
        return int(str(candidate)) >= int(str(current))
    except (TypeError, ValueError):
        return float(candidate_at or 0) >= float(current_at or 0)


def record_inbound_activity(
    phone_number: str,
    inbound_uid,
    session_key: str,
    *,
    storage=None,
    now: float | None = None,
    client_id=None,
    channel_id=None,
    transport: str | None = None,
) -> dict[str, Any]:
    """Persist the newest accepted inbound so every replica sees the same activity."""
    key = normalize_phone_key(phone_number)
    uid = str(inbound_uid or "")
    timestamp = float(now if now is not None else time.time())

    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.setdefault(key, _blank_state(key))
            if _uid_is_at_least(
                uid,
                state.get("last_inbound_uid"),
                timestamp,
                state.get("last_inbound_at"),
            ):
                is_newer = uid != state.get("last_inbound_uid")
                state["last_inbound_uid"] = uid
                state["last_inbound_at"] = timestamp
                state["session_key"] = session_key
                if client_id not in (None, ""):
                    state["client_id"] = str(client_id)
                if channel_id not in (None, ""):
                    state["channel_id"] = str(channel_id)
                if transport:
                    state["transport"] = str(transport)
                if is_newer:
                    state["inactivity_claim_uid"] = None
                    state["inactivity_failure_count"] = 0
                    state["inactivity_next_retry_at"] = None
                    state["inactivity_terminal"] = False
                state["updated_at"] = timestamp
            return state.copy()

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {LIFECYCLE_TABLE}
                    (phone_number, last_inbound_uid, last_inbound_at, session_key,
                     greeted_session_key, inactivity_claim_uid,
                     inactivity_closed_for_uid, reopen_greeting_pending,
                     client_id, channel_id, transport, inactivity_failure_count,
                     inactivity_next_retry_at, inactivity_terminal, updated_at)
                VALUES (%s, %s, %s, %s, NULL, NULL, NULL, FALSE,
                        %s, %s, %s, 0, NULL, FALSE, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    last_inbound_uid = EXCLUDED.last_inbound_uid,
                    last_inbound_at = EXCLUDED.last_inbound_at,
                    session_key = EXCLUDED.session_key,
                    client_id = COALESCE(EXCLUDED.client_id, {LIFECYCLE_TABLE}.client_id),
                    channel_id = COALESCE(EXCLUDED.channel_id, {LIFECYCLE_TABLE}.channel_id),
                    transport = COALESCE(EXCLUDED.transport, {LIFECYCLE_TABLE}.transport),
                    inactivity_claim_uid = CASE
                        WHEN {LIFECYCLE_TABLE}.last_inbound_uid IS DISTINCT FROM EXCLUDED.last_inbound_uid
                        THEN NULL
                        ELSE {LIFECYCLE_TABLE}.inactivity_claim_uid
                    END,
                    inactivity_failure_count = CASE
                        WHEN {LIFECYCLE_TABLE}.last_inbound_uid IS DISTINCT FROM EXCLUDED.last_inbound_uid
                        THEN 0 ELSE {LIFECYCLE_TABLE}.inactivity_failure_count END,
                    inactivity_next_retry_at = CASE
                        WHEN {LIFECYCLE_TABLE}.last_inbound_uid IS DISTINCT FROM EXCLUDED.last_inbound_uid
                        THEN NULL ELSE {LIFECYCLE_TABLE}.inactivity_next_retry_at END,
                    inactivity_terminal = CASE
                        WHEN {LIFECYCLE_TABLE}.last_inbound_uid IS DISTINCT FROM EXCLUDED.last_inbound_uid
                        THEN FALSE ELSE {LIFECYCLE_TABLE}.inactivity_terminal END,
                    updated_at = EXCLUDED.updated_at
                WHERE CASE
                    WHEN EXCLUDED.last_inbound_uid ~ '^[0-9]+$'
                     AND {LIFECYCLE_TABLE}.last_inbound_uid ~ '^[0-9]+$'
                    THEN EXCLUDED.last_inbound_uid::NUMERIC >= {LIFECYCLE_TABLE}.last_inbound_uid::NUMERIC
                    ELSE EXCLUDED.last_inbound_at >= {LIFECYCLE_TABLE}.last_inbound_at
                END
                RETURNING phone_number, last_inbound_uid, last_inbound_at, session_key,
                          greeted_session_key, inactivity_claim_uid,
                          inactivity_closed_for_uid, reopen_greeting_pending,
                          client_id, channel_id, transport, inactivity_failure_count,
                          inactivity_next_retry_at, inactivity_terminal, updated_at
                """,
                (
                    key, uid, timestamp, session_key,
                    str(client_id) if client_id not in (None, "") else None,
                    str(channel_id) if channel_id not in (None, "") else None,
                    str(transport) if transport else None,
                    timestamp,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    f"""
                    SELECT phone_number, last_inbound_uid, last_inbound_at, session_key,
                           greeted_session_key, inactivity_claim_uid,
                           inactivity_closed_for_uid, reopen_greeting_pending,
                           client_id, channel_id, transport, inactivity_failure_count,
                           inactivity_next_retry_at, inactivity_terminal, updated_at
                    FROM {LIFECYCLE_TABLE}
                    WHERE phone_number = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        conn.commit()
        state = _row_to_state(row) or _blank_state(key)
        with _memory_lock:
            _memory_state[key] = state.copy()
        return state
    except Exception as error:
        logger.error("No se pudo registrar actividad para %s: %s", key, error)
        return record_inbound_activity(
            key,
            uid,
            session_key,
            storage=None,
            now=timestamp,
            client_id=client_id,
            channel_id=channel_id,
            transport=transport,
        )
    finally:
        if conn is not None:
            conn.close()


def get_lifecycle_state(phone_number: str, *, storage=None) -> dict[str, Any] | None:
    key = normalize_phone_key(phone_number)
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.get(key)
            return state.copy() if state else None

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT phone_number, last_inbound_uid, last_inbound_at, session_key,
                       greeted_session_key, inactivity_claim_uid,
                       inactivity_closed_for_uid, reopen_greeting_pending,
                       client_id, channel_id, transport, inactivity_failure_count,
                       inactivity_next_retry_at, inactivity_terminal, updated_at
                FROM {LIFECYCLE_TABLE}
                WHERE phone_number = %s
                """,
                (key,),
            )
            state = _row_to_state(cursor.fetchone())
        if state:
            with _memory_lock:
                _memory_state[key] = state.copy()
        return state
    except Exception as error:
        logger.error("No se pudo consultar lifecycle para %s: %s", key, error)
        with _memory_lock:
            state = _memory_state.get(key)
            return state.copy() if state else None
    finally:
        if conn is not None:
            conn.close()


def reset_conversation_lifecycle(phone_number: str, *, storage=None) -> bool:
    """Remove all durable and local lifecycle state for an administrative reset."""
    key = normalize_phone_key(phone_number)
    with _memory_lock:
        memory_removed = _memory_state.pop(key, None) is not None

    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        return memory_removed

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {LIFECYCLE_TABLE} WHERE phone_number = %s",
                (key,),
            )
            database_removed = cursor.rowcount > 0
        conn.commit()
        return database_removed or memory_removed
    except Exception as error:
        logger.error("No se pudo reiniciar lifecycle para %s: %s", key, error)
        return memory_removed
    finally:
        if conn is not None:
            conn.close()


def claim_session_greeting(
    phone_number: str,
    session_key: str,
    *,
    boundary_requested: bool,
    storage=None,
) -> bool:
    """Atomically claim the one institutional greeting for a session boundary."""
    key = normalize_phone_key(phone_number)
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.setdefault(key, _blank_state(key))
            should_claim = bool(state.get("reopen_greeting_pending")) or (
                boundary_requested and state.get("greeted_session_key") != session_key
            )
            if not should_claim:
                return False
            state["greeted_session_key"] = session_key
            state["reopen_greeting_pending"] = False
            state["updated_at"] = time.time()
            return True

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {LIFECYCLE_TABLE}
                SET greeted_session_key = %s,
                    reopen_greeting_pending = FALSE,
                    updated_at = %s
                WHERE phone_number = %s
                  AND (
                      reopen_greeting_pending = TRUE
                      OR (%s = TRUE AND greeted_session_key IS DISTINCT FROM %s)
                  )
                RETURNING phone_number
                """,
                (session_key, time.time(), key, bool(boundary_requested), session_key),
            )
            row = cursor.fetchone()
        conn.commit()
        return bool(row)
    except Exception as error:
        logger.error("No se pudo reclamar saludo de sesión para %s: %s", key, error)
        return claim_session_greeting(
            key,
            session_key,
            boundary_requested=boundary_requested,
            storage=None,
        )
    finally:
        if conn is not None:
            conn.close()


def mark_session_greeting_sent(phone_number: str, session_key: str, *, storage=None) -> None:
    """Record a greeting sent by the atomic return-to-SAM handler."""
    key = normalize_phone_key(phone_number)
    timestamp = time.time()
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.setdefault(key, _blank_state(key))
            state["greeted_session_key"] = session_key
            state["reopen_greeting_pending"] = False
            state["updated_at"] = timestamp
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {LIFECYCLE_TABLE}
                    (phone_number, greeted_session_key, reopen_greeting_pending, updated_at)
                VALUES (%s, %s, FALSE, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    greeted_session_key = EXCLUDED.greeted_session_key,
                    reopen_greeting_pending = FALSE,
                    updated_at = EXCLUDED.updated_at
                """,
                (key, session_key, timestamp),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo registrar saludo enviado para %s: %s", key, error)
        mark_session_greeting_sent(key, session_key, storage=None)
    finally:
            if conn is not None:
                conn.close()


def mark_reopen_greeting_pending(
    phone_number: str,
    *,
    storage=None,
    reset_activity: bool = False,
) -> None:
    """Persist that the next inbound must receive a boundary greeting.

    ``reset_activity`` is used when control returns from a human. No inactivity
    timer may run again until a real client inbound starts the new bot session.
    """
    key = normalize_phone_key(phone_number)
    timestamp = time.time()
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.setdefault(key, _blank_state(key))
            state["reopen_greeting_pending"] = True
            if reset_activity:
                state["last_inbound_uid"] = None
                state["last_inbound_at"] = None
                state["inactivity_claim_uid"] = None
            state["updated_at"] = timestamp
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {LIFECYCLE_TABLE}
                    (phone_number, reopen_greeting_pending, updated_at)
                VALUES (%s, TRUE, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    reopen_greeting_pending = TRUE,
                    last_inbound_uid = CASE
                        WHEN %s THEN NULL
                        ELSE {LIFECYCLE_TABLE}.last_inbound_uid
                    END,
                    last_inbound_at = CASE
                        WHEN %s THEN NULL
                        ELSE {LIFECYCLE_TABLE}.last_inbound_at
                    END,
                    inactivity_claim_uid = CASE
                        WHEN %s THEN NULL
                        ELSE {LIFECYCLE_TABLE}.inactivity_claim_uid
                    END,
                    updated_at = EXCLUDED.updated_at
                """,
                (key, timestamp, reset_activity, reset_activity, reset_activity),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo marcar saludo pendiente para %s: %s", key, error)
        mark_reopen_greeting_pending(
            key,
            storage=None,
            reset_activity=reset_activity,
        )
    finally:
        if conn is not None:
            conn.close()


def list_inactivity_candidates(
    *,
    threshold_seconds: float,
    storage=None,
    now: float | None = None,
    limit: int = 100,
) -> list[str]:
    """List durable conversations eligible for an inactivity close."""
    timestamp = float(now if now is not None else time.time())
    cutoff = timestamp - float(threshold_seconds)

    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            return [
                phone
                for phone, state in _memory_state.items()
                if state.get("last_inbound_uid") is not None
                and state.get("last_inbound_at") is not None
                and float(state["last_inbound_at"]) <= cutoff
                and not state.get("inactivity_claim_uid")
                and state.get("inactivity_closed_for_uid")
                != state.get("last_inbound_uid")
                and not state.get("inactivity_terminal")
                and float(state.get("inactivity_next_retry_at") or 0) <= timestamp
            ][: max(1, int(limit))]

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT phone_number
                FROM {LIFECYCLE_TABLE}
                WHERE last_inbound_uid IS NOT NULL
                  AND last_inbound_at <= %s
                  AND inactivity_claim_uid IS NULL
                  AND inactivity_closed_for_uid IS DISTINCT FROM last_inbound_uid
                  AND inactivity_terminal = FALSE
                  AND (inactivity_next_retry_at IS NULL OR inactivity_next_retry_at <= %s)
                ORDER BY last_inbound_at ASC
                LIMIT %s
                """,
                (cutoff, timestamp, max(1, int(limit))),
            )
            return [str(row[0]) for row in cursor.fetchall()]
    except Exception as error:
        logger.error("No se pudieron listar candidatos de inactividad: %s", error)
        return list_inactivity_candidates(
            threshold_seconds=threshold_seconds,
            storage=None,
            now=timestamp,
            limit=limit,
        )
    finally:
        if conn is not None:
            conn.close()


def claim_inactivity_close(
    phone_number: str,
    *,
    threshold_seconds: float,
    storage=None,
    now: float | None = None,
) -> str | None:
    """Atomically claim an inactivity close for the latest durable inbound."""
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    cutoff = timestamp - float(threshold_seconds)

    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.get(key)
            if not state or state.get("last_inbound_at") is None:
                return None
            uid = state.get("last_inbound_uid")
            if (
                float(state["last_inbound_at"]) > cutoff
                or state.get("inactivity_claim_uid")
                or state.get("inactivity_closed_for_uid") == uid
                or state.get("inactivity_terminal")
                or float(state.get("inactivity_next_retry_at") or 0) > timestamp
            ):
                return None
            state["inactivity_claim_uid"] = uid
            state["updated_at"] = timestamp
            return str(uid)

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {LIFECYCLE_TABLE}
                SET inactivity_claim_uid = last_inbound_uid,
                    updated_at = %s
                WHERE phone_number = %s
                  AND last_inbound_uid IS NOT NULL
                  AND last_inbound_at <= %s
                  AND inactivity_claim_uid IS NULL
                  AND inactivity_closed_for_uid IS DISTINCT FROM last_inbound_uid
                  AND inactivity_terminal = FALSE
                  AND (inactivity_next_retry_at IS NULL OR inactivity_next_retry_at <= %s)
                RETURNING last_inbound_uid
                """,
                (timestamp, key, cutoff, timestamp),
            )
            row = cursor.fetchone()
        conn.commit()
        return str(row[0]) if row else None
    except Exception as error:
        logger.error("No se pudo reclamar cierre de inactividad para %s: %s", key, error)
        return claim_inactivity_close(
            key,
            threshold_seconds=threshold_seconds,
            storage=None,
            now=timestamp,
        )
    finally:
        if conn is not None:
            conn.close()


def inactivity_claim_is_current(phone_number: str, claim_uid: str, *, storage=None) -> bool:
    state = get_lifecycle_state(phone_number, storage=storage)
    return bool(
        state
        and str(state.get("last_inbound_uid")) == str(claim_uid)
        and str(state.get("inactivity_claim_uid")) == str(claim_uid)
    )


def mark_inactivity_close_sent(phone_number: str, claim_uid: str, *, storage=None) -> bool:
    """Finalize a claimed close only if no newer inbound arrived during I/O."""
    key = normalize_phone_key(phone_number)
    timestamp = time.time()
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.get(key)
            if not state or not inactivity_claim_is_current(key, claim_uid, storage=None):
                return False
            state["inactivity_claim_uid"] = None
            state["inactivity_closed_for_uid"] = str(claim_uid)
            state["reopen_greeting_pending"] = True
            state["inactivity_failure_count"] = 0
            state["inactivity_next_retry_at"] = None
            state["inactivity_terminal"] = False
            state["updated_at"] = timestamp
            return True

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {LIFECYCLE_TABLE}
                SET inactivity_claim_uid = NULL,
                    inactivity_closed_for_uid = %s,
                    reopen_greeting_pending = TRUE,
                    inactivity_failure_count = 0,
                    inactivity_next_retry_at = NULL,
                    inactivity_terminal = FALSE,
                    updated_at = %s
                WHERE phone_number = %s
                  AND last_inbound_uid = %s
                  AND inactivity_claim_uid = %s
                RETURNING phone_number
                """,
                (str(claim_uid), timestamp, key, str(claim_uid), str(claim_uid)),
            )
            row = cursor.fetchone()
        conn.commit()
        return bool(row)
    except Exception as error:
        logger.error("No se pudo finalizar cierre de inactividad para %s: %s", key, error)
        return False
    finally:
        if conn is not None:
            conn.close()


def release_inactivity_claim(phone_number: str, claim_uid: str, *, storage=None) -> None:
    key = normalize_phone_key(phone_number)
    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.get(key)
            if state and str(state.get("inactivity_claim_uid")) == str(claim_uid):
                state["inactivity_claim_uid"] = None
                state["updated_at"] = time.time()
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {LIFECYCLE_TABLE}
                SET inactivity_claim_uid = NULL,
                    updated_at = %s
                WHERE phone_number = %s AND inactivity_claim_uid = %s
                """,
                (time.time(), key, str(claim_uid)),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo liberar claim de inactividad para %s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()


def mark_inactivity_failure(
    phone_number: str,
    claim_uid: str,
    *,
    storage=None,
    now: float | None = None,
    terminal: bool = False,
    base_delay_seconds: float = 300,
    max_delay_seconds: float = 3600,
) -> None:
    """Release a failed inactivity claim with backoff, or quarantine it."""
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())

    if storage is None or not ensure_conversation_lifecycle_storage(storage):
        with _memory_lock:
            state = _memory_state.get(key)
            if not state or str(state.get("inactivity_claim_uid")) != str(claim_uid):
                return
            failures = int(state.get("inactivity_failure_count") or 0) + 1
            delay = min(
                float(max_delay_seconds),
                float(base_delay_seconds) * (2 ** (failures - 1)),
            )
            state["inactivity_claim_uid"] = None
            state["inactivity_failure_count"] = failures
            state["inactivity_next_retry_at"] = None if terminal else timestamp + delay
            state["inactivity_terminal"] = bool(terminal)
            state["updated_at"] = timestamp
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {LIFECYCLE_TABLE}
                SET inactivity_claim_uid = NULL,
                    inactivity_failure_count = inactivity_failure_count + 1,
                    inactivity_next_retry_at = CASE
                        WHEN %s THEN NULL
                        ELSE %s + LEAST(%s, %s * POWER(2, inactivity_failure_count))
                    END,
                    inactivity_terminal = %s,
                    updated_at = %s
                WHERE phone_number = %s AND inactivity_claim_uid = %s
                """,
                (
                    bool(terminal), timestamp, float(max_delay_seconds),
                    float(base_delay_seconds), bool(terminal), timestamp,
                    key, str(claim_uid),
                ),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo registrar fallo de inactividad para %s: %s", key, error)
        mark_inactivity_failure(
            key,
            claim_uid,
            storage=None,
            now=timestamp,
            terminal=terminal,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
    finally:
        if conn is not None:
            conn.close()
