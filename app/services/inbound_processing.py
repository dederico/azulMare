import threading
import time
import uuid

try:
    import psycopg2
except ImportError:  # Permite pruebas y desarrollo sin PostgreSQL.
    psycopg2 = None

try:
    from app.util.logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


CLAIM_TABLE = "inbound_processing_claims"
DEFAULT_LEASE_SECONDS = 3 * 60
CLAIM_RETENTION_SECONDS = 24 * 60 * 60

_memory_claims = {}
_memory_lock = threading.RLock()
_schema_lock = threading.Lock()
_schema_ready = False


def _claim_is_newer(candidate_uid, candidate_claimed_at, current_uid, current_claimed_at) -> bool:
    try:
        return int(str(candidate_uid)) > int(str(current_uid))
    except (TypeError, ValueError):
        return float(candidate_claimed_at or 0) > float(current_claimed_at or 0)


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


def ensure_inbound_processing_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {CLAIM_TABLE} (
                        inbound_uid TEXT PRIMARY KEY,
                        phone_number TEXT,
                        claim_token TEXT NOT NULL,
                        status TEXT NOT NULL,
                        claimed_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.error("No se pudo preparar deduplicación distribuida de inbound: %s", error)
            return False
        finally:
            if conn is not None:
                conn.close()


def _claim_in_memory(
    uid: str,
    phone_number: str,
    token: str,
    now: float,
    lease_seconds: float,
):
    with _memory_lock:
        existing = _memory_claims.get(uid)
        if existing:
            is_delivered = existing.get("status") == "delivered"
            is_active = now - float(existing.get("claimed_at") or 0) < lease_seconds
            if is_delivered or is_active:
                return None

        _memory_claims[uid] = {
            "phone_number": phone_number,
            "claim_token": token,
            "status": "processing",
            "claimed_at": now,
            "updated_at": now,
        }
        return token


def claim_inbound_processing(
    uid,
    phone_number: str,
    *,
    storage=None,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
) -> str | None:
    """Atomically claim an inbound so only one replica processes it."""
    if uid in (None, ""):
        return None

    key = str(uid)
    token = uuid.uuid4().hex
    now = time.time()
    lease_seconds = max(float(lease_seconds), 1.0)

    if storage is None or not ensure_inbound_processing_storage(storage):
        return _claim_in_memory(
            key,
            str(phone_number or ""),
            token,
            now,
            lease_seconds,
        )

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {CLAIM_TABLE} WHERE updated_at < %s",
                (now - CLAIM_RETENTION_SECONDS,),
            )
            cursor.execute(
                f"""
                INSERT INTO {CLAIM_TABLE}
                    (inbound_uid, phone_number, claim_token, status, claimed_at, updated_at)
                VALUES (%s, %s, %s, 'processing', %s, %s)
                ON CONFLICT (inbound_uid) DO NOTHING
                RETURNING claim_token
                """,
                (key, str(phone_number or ""), token, now, now),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    f"""
                    UPDATE {CLAIM_TABLE}
                    SET phone_number = %s,
                        claim_token = %s,
                        status = 'processing',
                        claimed_at = %s,
                        updated_at = %s
                    WHERE inbound_uid = %s
                      AND status = 'processing'
                      AND claimed_at <= %s
                    RETURNING claim_token
                    """,
                    (
                        str(phone_number or ""),
                        token,
                        now,
                        now,
                        key,
                        now - lease_seconds,
                    ),
                )
                row = cursor.fetchone()
        conn.commit()

        if row is None:
            return None

        with _memory_lock:
            _memory_claims[key] = {
                "phone_number": str(phone_number or ""),
                "claim_token": token,
                "status": "processing",
                "claimed_at": now,
                "updated_at": now,
            }
        return token
    except Exception as error:
        logger.error("No se pudo reclamar inbound uid=%s: %s", key, error)
        return _claim_in_memory(
            key,
            str(phone_number or ""),
            token,
            now,
            lease_seconds,
        )
    finally:
        if conn is not None:
            conn.close()


def is_latest_inbound_processing_claim(
    uid,
    phone_number: str,
    claim_token: str | None,
    *,
    storage=None,
) -> bool:
    """Check that no newer inbound for this phone started while this one ran."""
    if uid in (None, "") or not claim_token:
        return False

    key = str(uid)
    phone_key = str(phone_number or "")

    if storage is None or not ensure_inbound_processing_storage(storage):
        with _memory_lock:
            current = _memory_claims.get(key)
            if not current or current.get("claim_token") != claim_token:
                return False
            current_claimed_at = float(current.get("claimed_at") or 0)
            return not any(
                row.get("phone_number") == phone_key
                and _claim_is_newer(
                    candidate_uid,
                    row.get("claimed_at"),
                    key,
                    current_claimed_at,
                )
                for candidate_uid, row in _memory_claims.items()
            )

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT NOT EXISTS (
                    SELECT 1
                    FROM {CLAIM_TABLE} newer
                    JOIN {CLAIM_TABLE} current
                      ON current.inbound_uid = %s
                     AND current.claim_token = %s
                    WHERE newer.phone_number = %s
                      AND CASE
                          WHEN newer.inbound_uid ~ '^[0-9]+$'
                           AND current.inbound_uid ~ '^[0-9]+$'
                          THEN newer.inbound_uid::NUMERIC > current.inbound_uid::NUMERIC
                          ELSE newer.claimed_at > current.claimed_at
                      END
                )
                AND EXISTS (
                    SELECT 1 FROM {CLAIM_TABLE}
                    WHERE inbound_uid = %s AND claim_token = %s
                )
                """,
                (key, claim_token, phone_key, key, claim_token),
            )
            row = cursor.fetchone()
        return bool(row and row[0])
    except Exception as error:
        logger.error("No se pudo validar orden de inbound uid=%s: %s", key, error)
        return False
    finally:
        if conn is not None:
            conn.close()


def mark_inbound_processing_delivered(uid, claim_token: str | None, *, storage=None) -> None:
    if uid in (None, "") or not claim_token:
        return

    key = str(uid)
    now = time.time()
    with _memory_lock:
        existing = _memory_claims.get(key)
        if existing and existing.get("claim_token") == claim_token:
            existing["status"] = "delivered"
            existing["updated_at"] = now

    if storage is None or not ensure_inbound_processing_storage(storage):
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {CLAIM_TABLE}
                SET status = 'delivered', updated_at = %s
                WHERE inbound_uid = %s AND claim_token = %s
                """,
                (now, key, claim_token),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo confirmar entrega distribuida uid=%s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()


def release_inbound_processing_claim(uid, claim_token: str | None, *, storage=None) -> None:
    """Release only the worker's own unfinished claim so a failed inbound can retry."""
    if uid in (None, "") or not claim_token:
        return

    key = str(uid)
    with _memory_lock:
        existing = _memory_claims.get(key)
        if existing and existing.get("claim_token") == claim_token:
            _memory_claims.pop(key, None)

    if storage is None or not ensure_inbound_processing_storage(storage):
        return

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM {CLAIM_TABLE}
                WHERE inbound_uid = %s
                  AND claim_token = %s
                  AND status = 'processing'
                """,
                (key, claim_token),
            )
        conn.commit()
    except Exception as error:
        logger.error("No se pudo liberar claim fallido uid=%s: %s", key, error)
    finally:
        if conn is not None:
            conn.close()
