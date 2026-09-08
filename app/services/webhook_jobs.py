import hashlib
import json
import threading
import time
import uuid
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover - production installs psycopg2
    psycopg2 = None
    Json = None

from app.util.logger import logger


WEBHOOK_JOBS_TABLE = "chat2desk_webhook_jobs"
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


def ensure_webhook_job_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {WEBHOOK_JOBS_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        event_key TEXT UNIQUE NOT NULL,
                        conversation_key TEXT,
                        payload JSONB NOT NULL,
                        query_params JSONB NOT NULL DEFAULT '{{}}'::jsonb,
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
                    f"ALTER TABLE {WEBHOOK_JOBS_TABLE} ADD COLUMN IF NOT EXISTS conversation_key TEXT"
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{WEBHOOK_JOBS_TABLE}_ready
                    ON {WEBHOOK_JOBS_TABLE} (status, available_at, id)
                    """
                )
                cursor.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{WEBHOOK_JOBS_TABLE}_conversation
                    ON {WEBHOOK_JOBS_TABLE} (conversation_key, id, status)
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception("No se pudo preparar la cola durable de webhooks: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def build_webhook_event_key(payload: dict[str, Any]) -> str:
    message_id = payload.get("message_id")
    hook_type = payload.get("hook_type") or "unknown"
    message_type = payload.get("type") or "unknown"
    if message_id not in (None, ""):
        return f"{hook_type}:{message_type}:{message_id}"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{hook_type}:{message_type}:sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def enqueue_webhook_job(storage, payload: dict[str, Any], query_params=None) -> tuple[bool, str]:
    if not ensure_webhook_job_storage(storage):
        raise RuntimeError("cola durable no disponible")
    event_key = build_webhook_event_key(payload)
    conversation_key = str(
        (payload.get("client") or {}).get("phone")
        or payload.get("client_id")
        or payload.get("dialog_id")
        or "unknown"
    )
    timestamp = time.time()
    stored_payload = dict(payload)
    stored_payload["_sam_webhook_received_at"] = timestamp
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {WEBHOOK_JOBS_TABLE}
                    (event_key, conversation_key, payload, query_params, status, attempts,
                     available_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'queued', 0, %s, %s, %s)
                ON CONFLICT (event_key) DO NOTHING
                RETURNING id
                """,
                (
                    event_key,
                    conversation_key,
                    Json(stored_payload),
                    Json(dict(query_params or {})),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            inserted = cursor.fetchone() is not None
        conn.commit()
        return inserted, event_key
    finally:
        if conn is not None:
            conn.close()


def claim_webhook_job(storage, *, stale_after_seconds: float = 300) -> dict[str, Any] | None:
    if not ensure_webhook_job_storage(storage):
        return None
    timestamp = time.time()
    claim_token = uuid.uuid4().hex
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                WITH candidate AS (
                    SELECT candidate_jobs.id
                    FROM {WEBHOOK_JOBS_TABLE} AS candidate_jobs
                    WHERE ((
                        candidate_jobs.status IN ('queued', 'retry')
                        AND candidate_jobs.available_at <= %s
                        AND pg_try_advisory_xact_lock(
                            hashtextextended(COALESCE(candidate_jobs.conversation_key, ''), 0)
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM {WEBHOOK_JOBS_TABLE} AS older_jobs
                            WHERE older_jobs.conversation_key = candidate_jobs.conversation_key
                              AND older_jobs.id < candidate_jobs.id
                              AND older_jobs.status NOT IN ('done', 'dead')
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM {WEBHOOK_JOBS_TABLE} AS active_jobs
                            WHERE active_jobs.status = 'processing'
                              AND active_jobs.claimed_at > %s
                              AND active_jobs.conversation_key = candidate_jobs.conversation_key
                        )
                    ) OR (
                        candidate_jobs.status = 'processing'
                        AND candidate_jobs.claimed_at <= %s
                    ))
                    ORDER BY id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE {WEBHOOK_JOBS_TABLE} AS jobs
                SET status = 'processing',
                    attempts = attempts + 1,
                    claimed_at = %s,
                    claim_token = %s,
                    updated_at = %s
                FROM candidate
                WHERE jobs.id = candidate.id
                RETURNING jobs.id, jobs.event_key, jobs.payload,
                          jobs.query_params, jobs.attempts, jobs.claim_token
                """,
                (
                    timestamp,
                    timestamp - stale_after_seconds,
                    timestamp - stale_after_seconds,
                    timestamp,
                    claim_token,
                    timestamp,
                ),
            )
            row = cursor.fetchone()
        conn.commit()
        if not row:
            return None
        return {
            "id": row[0],
            "event_key": row[1],
            "payload": row[2],
            "query_params": row[3] or {},
            "attempts": int(row[4]),
            "claim_token": row[5],
        }
    finally:
        if conn is not None:
            conn.close()


def complete_webhook_job(storage, job_id: int, claim_token: str) -> bool:
    return _finish_job(storage, job_id, claim_token, status="done")


def fail_webhook_job(
    storage,
    job_id: int,
    claim_token: str,
    error: Exception | str,
    *,
    attempts: int,
    max_attempts: int = 6,
) -> bool:
    terminal = attempts >= max_attempts
    delay = min(900.0, 5.0 * (2 ** max(0, attempts - 1)))
    return _finish_job(
        storage,
        job_id,
        claim_token,
        status="dead" if terminal else "retry",
        error=str(error)[:2000],
        available_at=None if terminal else time.time() + delay,
    )


def _finish_job(
    storage,
    job_id: int,
    claim_token: str,
    *,
    status: str,
    error: str | None = None,
    available_at: float | None = None,
) -> bool:
    timestamp = time.time()
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {WEBHOOK_JOBS_TABLE}
                SET status = %s,
                    available_at = COALESCE(%s, available_at),
                    claimed_at = NULL,
                    claim_token = NULL,
                    last_error = %s,
                    updated_at = %s
                WHERE id = %s AND claim_token = %s
                """,
                (status, available_at, error, timestamp, job_id, claim_token),
            )
            changed = cursor.rowcount == 1
        conn.commit()
        return changed
    finally:
        if conn is not None:
            conn.close()
