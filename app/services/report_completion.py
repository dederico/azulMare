import json
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
REPORT_COMPLETION_RETENTION_SECONDS = 30 * 60

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
                        notified_at DOUBLE PRECISION,
                        report_snapshot TEXT,
                        expires_at DOUBLE PRECISION
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
                    ("report_snapshot", "TEXT"),
                    ("expires_at", "DOUBLE PRECISION"),
                ):
                    cursor.execute(
                        f"ALTER TABLE {REPORT_COMPLETION_TABLE} "
                        f"ADD COLUMN IF NOT EXISTS {column} {definition}"
                    )
                cursor.execute(
                    f"UPDATE {REPORT_COMPLETION_TABLE} "
                    "SET expires_at = completed_at + %s "
                    "WHERE expires_at IS NULL",
                    (REPORT_COMPLETION_RETENTION_SECONDS,),
                )
                cursor.execute(
                    f"DELETE FROM {REPORT_COMPLETION_TABLE} "
                    "WHERE expires_at <= %s",
                    (time.time(),),
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"idx_{REPORT_COMPLETION_TABLE}_expires_at "
                    f"ON {REPORT_COMPLETION_TABLE} (expires_at)"
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


def _minimize_report_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Retain only the 30-minute continuity facts, never names or media URLs."""
    source = snapshot or {}

    def safe_nonnegative_int(value, fallback=0) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return max(0, int(fallback))

    minimized = {
        key: str(source.get(key) or "")[:500]
        for key in (
            "selection1", "selection4", "selection5", "selection6",
            "selection7",
        )
    }
    minimized["image_count"] = safe_nonnegative_int(
        source.get("image_count"),
        len(source.get("images") or []),
    )
    minimized["followup_count"] = safe_nonnegative_int(
        source.get("followup_count"),
    )
    if source.get("last_followup_at") is not None:
        minimized["last_followup_at"] = float(source["last_followup_at"])
    return minimized


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
    report_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = normalize_phone_key(phone_number)
    timestamp = float(now if now is not None else time.time())
    expires_at = timestamp + REPORT_COMPLETION_RETENTION_SECONDS
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
        "report_snapshot": _minimize_report_snapshot(report_snapshot),
        "expires_at": expires_at,
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
                     notified_at, report_snapshot, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
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
                    notified_at = NULL,
                    report_snapshot = EXCLUDED.report_snapshot,
                    expires_at = EXCLUDED.expires_at
                """,
                (
                    key, completion["folio"], timestamp, timestamp,
                    notification_message, request_id, origin_uid,
                    origin_message_id,
                    completion["client_id"], completion["channel_id"],
                    transport,
                    json.dumps(completion["report_snapshot"], ensure_ascii=False),
                    expires_at,
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
                           notified_at, report_snapshot, expires_at
                    FROM {REPORT_COMPLETION_TABLE}
                    WHERE phone_number = %s AND completed_at >= %s
                      AND expires_at > %s
                    """,
                    (key, cutoff, timestamp),
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
                    "report_snapshot": (
                        _minimize_report_snapshot(
                            json.loads(row[11]) if row[11] else {}
                        )
                    ),
                    "expires_at": float(row[12]),
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
        if (
            completion
            and float(completion.get("completed_at") or 0) >= cutoff
            and float(completion.get("expires_at") or 0) > timestamp
        ):
            return completion.copy()
        if completion and float(completion.get("expires_at") or 0) <= timestamp:
            _memory_completions.pop(key, None)
    return None


def purge_expired_report_completions(
    storage,
    *,
    now: float | None = None,
) -> int:
    """Physically purge expired continuity snapshots on a periodic cadence."""
    timestamp = float(now if now is not None else time.time())
    purged = 0
    with _memory_lock:
        expired_keys = [
            key for key, completion in _memory_completions.items()
            if float(completion.get("expires_at") or 0) <= timestamp
        ]
        for key in expired_keys:
            _memory_completions.pop(key, None)
        purged += len(expired_keys)

    if storage is None or not ensure_report_completion_storage(storage):
        return purged

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {REPORT_COMPLETION_TABLE} "
                "WHERE expires_at <= %s OR expires_at IS NULL",
                (timestamp,),
            )
            purged += max(0, int(cursor.rowcount or 0))
        conn.commit()
    except Exception as error:
        logger.error("No se pudieron purgar folios expirados: %s", error)
    finally:
        if conn is not None:
            conn.close()
    return purged


def append_report_completion_followup(
    storage,
    phone_number: str,
    message: str,
    *,
    now: float | None = None,
) -> bool:
    """Attach post-folio context to the durable incident snapshot."""
    key = normalize_phone_key(phone_number)
    compact = " ".join(str(message or "").split()).strip()
    if not compact:
        return False
    timestamp = float(now if now is not None else time.time())
    completion = None

    with _memory_lock:
        completion = _memory_completions.get(key)
        if completion:
            snapshot = _minimize_report_snapshot(completion.get("report_snapshot"))
            snapshot["followup_count"] = int(snapshot.get("followup_count") or 0) + 1
            snapshot["last_followup_at"] = timestamp
            completion["report_snapshot"] = snapshot

    if storage is None or not ensure_report_completion_storage(storage):
        return completion is not None

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT report_snapshot FROM {REPORT_COMPLETION_TABLE} "
                "WHERE phone_number = %s AND expires_at > %s FOR UPDATE",
                (key, timestamp),
            )
            row = cursor.fetchone()
            if not row:
                return False
            snapshot = _minimize_report_snapshot(
                json.loads(row[0]) if row[0] else {}
            )
            snapshot["followup_count"] = int(snapshot.get("followup_count") or 0) + 1
            snapshot["last_followup_at"] = timestamp
            cursor.execute(
                f"UPDATE {REPORT_COMPLETION_TABLE} "
                "SET report_snapshot = %s, updated_at = %s "
                "WHERE phone_number = %s",
                (json.dumps(snapshot, ensure_ascii=False), timestamp, key),
            )
        conn.commit()
        with _memory_lock:
            if key in _memory_completions:
                _memory_completions[key]["report_snapshot"] = snapshot
        return True
    except Exception as error:
        logger.error("No se pudo anexar seguimiento al folio para %s: %s", key, error)
        return False
    finally:
        if conn is not None:
            conn.close()


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


def report_session_supersedes_completion(
    completion: dict[str, Any] | None,
    report_session: dict[str, Any] | None,
) -> bool:
    """Return whether an active report generation started after a completion.

    A recent folio remains useful for rejecting genuinely delayed events from
    the report that just ended.  It must not, however, own media or control
    messages from a later report.  ``started_at`` is immutable for one report
    generation, unlike the legacy ``timestamp`` field which changes on every
    turn, so this comparison is the single ordering rule used by the inbound
    guards.
    """
    if not completion or not report_session:
        return False
    if report_session.get("report_intent_confirmed") is not True:
        return False
    try:
        completed_at = float(completion.get("completed_at") or 0)
        started_at = float(report_session.get("started_at") or 0)
    except (TypeError, ValueError, AttributeError):
        return False
    return bool(completed_at > 0 and started_at > completed_at)


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
