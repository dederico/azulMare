import json
import threading
import time
from datetime import datetime
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover
    psycopg2 = None
    Json = None

from app.services.conversation_control import normalize_phone_key
from app.util.logger import logger


REPORT_STATE_TABLE = "conversation_report_state"
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


def ensure_report_state_storage(storage) -> bool:
    global _schema_ready
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
                    CREATE TABLE IF NOT EXISTS {REPORT_STATE_TABLE} (
                        phone_number TEXT PRIMARY KEY,
                        report_session JSONB,
                        user_answers JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        conversation_epoch BIGINT NOT NULL DEFAULT 0,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    ALTER TABLE {REPORT_STATE_TABLE}
                    ADD COLUMN IF NOT EXISTS conversation_epoch BIGINT NOT NULL DEFAULT 0
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception("No se pudo preparar estado durable de reportes: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item)))


def save_report_state(
    storage,
    phone_number: str,
    report_session,
    answers,
    *,
    conversation_epoch: int = 0,
) -> bool:
    key = normalize_phone_key(phone_number)
    if not ensure_report_state_storage(storage):
        return False
    if not report_session and not answers:
        return delete_report_state(storage, key)

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {REPORT_STATE_TABLE}
                    (phone_number, report_session, user_answers, conversation_epoch, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (phone_number) DO UPDATE SET
                    report_session = EXCLUDED.report_session,
                    user_answers = EXCLUDED.user_answers,
                    conversation_epoch = EXCLUDED.conversation_epoch,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    key,
                    Json(_json_safe(report_session)) if report_session else None,
                    Json(_json_safe(answers or {})),
                    int(conversation_epoch),
                    time.time(),
                ),
            )
        conn.commit()
        return True
    finally:
        if conn is not None:
            conn.close()


def load_report_state(storage, phone_number: str) -> dict[str, Any] | None:
    key = normalize_phone_key(phone_number)
    if not ensure_report_state_storage(storage):
        return None
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT report_session, user_answers, conversation_epoch
                FROM {REPORT_STATE_TABLE}
                WHERE phone_number = %s
                """,
                (key,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        session = row[0]
        if session and session.get("timestamp") and isinstance(session["timestamp"], str):
            try:
                session["timestamp"] = datetime.fromisoformat(session["timestamp"])
            except ValueError:
                session["timestamp"] = None
        return {
            "report_session": session,
            "user_answers": row[1] or {},
            "conversation_epoch": int(row[2] or 0),
        }
    finally:
        if conn is not None:
            conn.close()


def delete_report_state(storage, phone_number: str) -> bool:
    key = normalize_phone_key(phone_number)
    if not ensure_report_state_storage(storage):
        return False
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {REPORT_STATE_TABLE} WHERE phone_number = %s",
                (key,),
            )
            changed = cursor.rowcount > 0
        conn.commit()
        return changed
    finally:
        if conn is not None:
            conn.close()
