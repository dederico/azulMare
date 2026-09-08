import threading
import time
import uuid

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None

from app.util.logger import logger


GREETING_OUTBOX_TABLE = "conversation_greeting_outbox"
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


def ensure_greeting_outbox_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {GREETING_OUTBOX_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        greeting_key TEXT UNIQUE NOT NULL,
                        phone_number TEXT NOT NULL,
                        client_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        transport TEXT NOT NULL,
                        message TEXT NOT NULL,
                        conversation_epoch BIGINT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'queued',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        available_at DOUBLE PRECISION NOT NULL,
                        claimed_at DOUBLE PRECISION,
                        claim_token TEXT,
                        last_error TEXT,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{GREETING_OUTBOX_TABLE}_ready
                    ON {GREETING_OUTBOX_TABLE} (status, available_at, id)
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception("No se pudo preparar outbox de saludos: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def enqueue_greeting(
    storage,
    *,
    greeting_key: str,
    phone_number: str,
    client_id,
    channel_id,
    transport: str,
    message: str,
    conversation_epoch: int,
) -> int:
    if not client_id or not channel_id:
        raise ValueError("client_id y channel_id son obligatorios para el saludo")
    if not ensure_greeting_outbox_storage(storage):
        raise RuntimeError("outbox de saludos no disponible")
    timestamp = time.time()
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {GREETING_OUTBOX_TABLE}
                    (greeting_key, phone_number, client_id, channel_id, transport,
                     message, conversation_epoch, status, attempts, available_at,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', 0, %s, %s, %s)
                ON CONFLICT (greeting_key) DO UPDATE SET
                    client_id = EXCLUDED.client_id,
                    channel_id = EXCLUDED.channel_id,
                    transport = EXCLUDED.transport,
                    message = EXCLUDED.message,
                    conversation_epoch = EXCLUDED.conversation_epoch,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                """,
                (
                    greeting_key, phone_number, str(client_id), str(channel_id),
                    transport, message, int(conversation_epoch), timestamp,
                    timestamp, timestamp,
                ),
            )
            row = cursor.fetchone()
        conn.commit()
        return int(row[0])
    finally:
        if conn is not None:
            conn.close()


def claim_greeting(
    storage,
    *,
    greeting_key: str | None = None,
    stale_after_seconds: float = 120,
) -> dict | None:
    if not ensure_greeting_outbox_storage(storage):
        return None
    timestamp = time.time()
    token = uuid.uuid4().hex
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                WITH candidate AS (
                    SELECT id FROM {GREETING_OUTBOX_TABLE}
                    WHERE (%s IS NULL OR greeting_key = %s)
                      AND ((status IN ('queued', 'retry') AND available_at <= %s)
                       OR (status = 'processing' AND claimed_at <= %s))
                    ORDER BY id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE {GREETING_OUTBOX_TABLE} AS items
                SET status = 'processing', attempts = attempts + 1,
                    claimed_at = %s, claim_token = %s, updated_at = %s
                FROM candidate
                WHERE items.id = candidate.id
                RETURNING items.id, items.greeting_key, items.phone_number,
                          items.client_id, items.channel_id, items.transport,
                          items.message, items.conversation_epoch, items.attempts,
                          items.claim_token
                """,
                (
                    greeting_key,
                    greeting_key,
                    timestamp,
                    timestamp - stale_after_seconds,
                    timestamp,
                    token,
                    timestamp,
                ),
            )
            row = cursor.fetchone()
        conn.commit()
        if not row:
            return None
        keys = (
            "id", "greeting_key", "phone_number", "client_id", "channel_id",
            "transport", "message", "conversation_epoch", "attempts", "claim_token",
        )
        return dict(zip(keys, row))
    finally:
        if conn is not None:
            conn.close()


def finish_greeting(
    storage,
    job_id: int,
    claim_token: str,
    *,
    success: bool,
    error: str | None = None,
    max_attempts: int = 8,
    attempts: int = 1,
    cancelled: bool = False,
) -> bool:
    timestamp = time.time()
    terminal = not success and attempts >= max_attempts
    status = "cancelled" if cancelled else ("sent" if success else ("dead" if terminal else "retry"))
    delay = min(900.0, 5.0 * (2 ** max(0, attempts - 1)))
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {GREETING_OUTBOX_TABLE}
                SET status = %s,
                    available_at = %s,
                    claimed_at = NULL,
                    claim_token = NULL,
                    last_error = %s,
                    updated_at = %s
                WHERE id = %s AND claim_token = %s
                """,
                (
                    status,
                    timestamp if success or terminal or cancelled else timestamp + delay,
                    (error or "")[:2000] or None,
                    timestamp,
                    job_id,
                    claim_token,
                ),
            )
            changed = cursor.rowcount == 1
        conn.commit()
        return changed
    finally:
        if conn is not None:
            conn.close()


def get_greeting_status(storage, greeting_key: str) -> str | None:
    if not ensure_greeting_outbox_storage(storage):
        return None
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT status FROM {GREETING_OUTBOX_TABLE} WHERE greeting_key = %s",
                (greeting_key,),
            )
            row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        if conn is not None:
            conn.close()
