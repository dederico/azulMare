"""Durable routing and transition deduplication for CIAC status callbacks.

The folio is the stable identity shared with CIAC.  Phone numbers are not a
safe outbound route once the same citizen can exist in more than one
Chat2Desk channel, so the route used to create the report is retained here.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

try:
    import psycopg2
except ImportError:  # pragma: no cover - production installs psycopg2
    psycopg2 = None

from app.util.logger import logger


REPORT_STATUS_DELIVERY_TABLE = "ciac_report_status_deliveries"
REPORT_STATUS_CLAIM_TTL_SECONDS = 10 * 60

_memory_rows: dict[str, dict[str, Any]] = {}
_memory_lock = threading.RLock()
_schema_lock = threading.Lock()
_schema_ready = False


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _connect(storage):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 no esta instalado")
    return psycopg2.connect(
        dbname=storage.dbName,
        user=storage.user,
        password=storage.password,
        host=storage.host,
        port=storage.port,
    )


def ensure_report_status_delivery_storage(storage) -> bool:
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
                    CREATE TABLE IF NOT EXISTS {REPORT_STATUS_DELIVERY_TABLE} (
                        folio TEXT PRIMARY KEY,
                        conversation_key TEXT,
                        contact_phone TEXT,
                        client_id TEXT,
                        channel_id TEXT,
                        transport TEXT,
                        last_status TEXT,
                        delivery_state TEXT,
                        claim_token TEXT,
                        claimed_at DOUBLE PRECISION,
                        provider_message_id TEXT,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                    """
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"idx_{REPORT_STATUS_DELIVERY_TABLE}_updated_at "
                    f"ON {REPORT_STATUS_DELIVERY_TABLE} (updated_at)"
                )
            conn.commit()
            _schema_ready = True
            return True
        except Exception as error:
            logger.exception(
                "No se pudo preparar la entrega durable de estados CIAC: %s",
                error,
            )
            return False
        finally:
            if conn is not None:
                conn.close()


def record_report_status_route(
    storage,
    folio: Any,
    *,
    conversation_key: Any = None,
    contact_phone: Any = None,
    client_id: Any,
    channel_id: Any,
    transport: Any,
    now: float | None = None,
) -> bool:
    """Retain the exact Chat2Desk route used when CIAC created the folio."""
    clean_folio = _clean(folio)
    clean_client_id = _clean(client_id)
    clean_channel_id = _clean(channel_id)
    clean_transport = _clean(transport)
    if not all((clean_folio, clean_client_id, clean_channel_id, clean_transport)):
        return False

    timestamp = float(now if now is not None else time.time())
    values = {
        "folio": clean_folio,
        "conversation_key": _clean(conversation_key),
        "contact_phone": _clean(contact_phone),
        "client_id": clean_client_id,
        "channel_id": clean_channel_id,
        "transport": clean_transport,
        "updated_at": timestamp,
    }
    with _memory_lock:
        existing = _memory_rows.get(clean_folio, {})
        _memory_rows[clean_folio] = {
            **existing,
            **{key: value for key, value in values.items() if value is not None},
            "created_at": existing.get("created_at", timestamp),
        }

    if storage is None or not ensure_report_status_delivery_storage(storage):
        return False

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {REPORT_STATUS_DELIVERY_TABLE}
                    (folio, conversation_key, contact_phone, client_id,
                     channel_id, transport, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (folio) DO UPDATE SET
                    conversation_key = COALESCE(
                        EXCLUDED.conversation_key,
                        {REPORT_STATUS_DELIVERY_TABLE}.conversation_key
                    ),
                    contact_phone = COALESCE(
                        EXCLUDED.contact_phone,
                        {REPORT_STATUS_DELIVERY_TABLE}.contact_phone
                    ),
                    client_id = EXCLUDED.client_id,
                    channel_id = EXCLUDED.channel_id,
                    transport = EXCLUDED.transport,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    clean_folio,
                    values["conversation_key"],
                    values["contact_phone"],
                    clean_client_id,
                    clean_channel_id,
                    clean_transport,
                    timestamp,
                    timestamp,
                ),
            )
        conn.commit()
        return True
    except Exception as error:
        logger.exception(
            "No se pudo guardar la ruta del folio %s: %s",
            clean_folio,
            error,
        )
        return False
    finally:
        if conn is not None:
            conn.close()


def _row_from_database(row) -> dict[str, Any] | None:
    if not row:
        return None
    keys = (
        "folio",
        "conversation_key",
        "contact_phone",
        "client_id",
        "channel_id",
        "transport",
        "last_status",
        "delivery_state",
        "claim_token",
        "claimed_at",
        "provider_message_id",
        "created_at",
        "updated_at",
    )
    return dict(zip(keys, row))


def get_report_status_delivery(storage, folio: Any) -> dict[str, Any] | None:
    clean_folio = _clean(folio)
    if not clean_folio:
        return None
    if storage is None:
        with _memory_lock:
            row = _memory_rows.get(clean_folio)
            return row.copy() if row else None
    if not ensure_report_status_delivery_storage(storage):
        return None

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT folio, conversation_key, contact_phone, client_id,
                       channel_id, transport, last_status, delivery_state,
                       claim_token, claimed_at, provider_message_id,
                       created_at, updated_at
                FROM {REPORT_STATUS_DELIVERY_TABLE}
                WHERE folio = %s
                """,
                (clean_folio,),
            )
            result = _row_from_database(cursor.fetchone())
        if result:
            with _memory_lock:
                _memory_rows[clean_folio] = result.copy()
        return result
    except Exception as error:
        logger.exception(
            "No se pudo consultar la ruta del folio %s: %s",
            clean_folio,
            error,
        )
        return None
    finally:
        if conn is not None:
            conn.close()


def claim_report_status_delivery(
    storage,
    folio: Any,
    status: Any,
    *,
    now: float | None = None,
    claim_ttl_seconds: float = REPORT_STATUS_CLAIM_TTL_SECONDS,
) -> str | None:
    """Claim one lifecycle transition, suppressing repeated same-state calls.

    A later different status is valid, so ``concluido -> reactivado ->
    concluido`` produces three deliveries while two consecutive ``concluido``
    callbacks produce one.
    """
    clean_folio = _clean(folio)
    clean_status = _clean(status)
    if not clean_folio or not clean_status:
        return None
    timestamp = float(now if now is not None else time.time())
    stale_before = timestamp - float(claim_ttl_seconds)
    token = uuid.uuid4().hex

    if storage is None:
        with _memory_lock:
            row = _memory_rows.get(clean_folio)
            if row is None:
                _memory_rows[clean_folio] = {
                    "folio": clean_folio,
                    "last_status": clean_status,
                    "delivery_state": "processing",
                    "claim_token": token,
                    "claimed_at": timestamp,
                    "provider_message_id": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                return token

            same_status = row.get("last_status") == clean_status
            state = row.get("delivery_state")
            active_processing = (
                state == "processing"
                and float(row.get("claimed_at") or 0) > stale_before
            )
            if active_processing:
                return None
            if same_status and state not in {"failed", "processing"}:
                return None
            row.update(
                last_status=clean_status,
                delivery_state="processing",
                claim_token=token,
                claimed_at=timestamp,
                provider_message_id=None,
                updated_at=timestamp,
            )
            return token

    if not ensure_report_status_delivery_storage(storage):
        return None

    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {REPORT_STATUS_DELIVERY_TABLE}
                    (folio, last_status, delivery_state, claim_token,
                     claimed_at, created_at, updated_at)
                VALUES (%s, %s, 'processing', %s, %s, %s, %s)
                ON CONFLICT (folio) DO NOTHING
                RETURNING claim_token
                """,
                (
                    clean_folio,
                    clean_status,
                    token,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            inserted = cursor.fetchone()
            if not inserted:
                cursor.execute(
                    f"""
                    UPDATE {REPORT_STATUS_DELIVERY_TABLE}
                    SET last_status = %s,
                        delivery_state = 'processing',
                        claim_token = %s,
                        claimed_at = %s,
                        provider_message_id = NULL,
                        updated_at = %s
                    WHERE folio = %s
                      AND (
                        (
                          last_status IS DISTINCT FROM %s
                          AND (
                            delivery_state IS DISTINCT FROM 'processing'
                            OR claimed_at IS NULL
                            OR claimed_at <= %s
                          )
                        )
                        OR (
                          last_status = %s
                          AND (
                            delivery_state = 'failed'
                            OR (
                              delivery_state = 'processing'
                              AND (claimed_at IS NULL OR claimed_at <= %s)
                            )
                          )
                        )
                      )
                    RETURNING claim_token
                    """,
                    (
                        clean_status,
                        token,
                        timestamp,
                        timestamp,
                        clean_folio,
                        clean_status,
                        stale_before,
                        clean_status,
                        stale_before,
                    ),
                )
                inserted = cursor.fetchone()
        conn.commit()
        if not inserted:
            return None
        with _memory_lock:
            row = _memory_rows.setdefault(
                clean_folio,
                {"folio": clean_folio, "created_at": timestamp},
            )
            row.update(
                last_status=clean_status,
                delivery_state="processing",
                claim_token=token,
                claimed_at=timestamp,
                provider_message_id=None,
                updated_at=timestamp,
            )
        return token
    except Exception as error:
        if conn is not None:
            conn.rollback()
        logger.exception(
            "No se pudo reclamar la entrega del folio %s: %s",
            clean_folio,
            error,
        )
        return None
    finally:
        if conn is not None:
            conn.close()


def _finish_claim(
    storage,
    folio: Any,
    claim_token: str,
    *,
    state: str,
    provider_message_id: Any = None,
    now: float | None = None,
) -> bool:
    clean_folio = _clean(folio)
    clean_token = _clean(claim_token)
    if not clean_folio or not clean_token:
        return False
    timestamp = float(now if now is not None else time.time())
    clean_provider_id = _clean(provider_message_id)

    if storage is None:
        with _memory_lock:
            row = _memory_rows.get(clean_folio)
            if not row or row.get("claim_token") != clean_token:
                return False
            row.update(
                delivery_state=state,
                provider_message_id=clean_provider_id,
                updated_at=timestamp,
            )
            return True

    if not ensure_report_status_delivery_storage(storage):
        return False
    conn = None
    try:
        conn = _connect(storage)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {REPORT_STATUS_DELIVERY_TABLE}
                SET delivery_state = %s,
                    provider_message_id = %s,
                    updated_at = %s
                WHERE folio = %s AND claim_token = %s
                RETURNING folio
                """,
                (
                    state,
                    clean_provider_id,
                    timestamp,
                    clean_folio,
                    clean_token,
                ),
            )
            updated = cursor.fetchone() is not None
        conn.commit()
        if updated:
            with _memory_lock:
                row = _memory_rows.setdefault(clean_folio, {"folio": clean_folio})
                row.update(
                    delivery_state=state,
                    provider_message_id=clean_provider_id,
                    updated_at=timestamp,
                )
        return updated
    except Exception as error:
        if conn is not None:
            conn.rollback()
        logger.exception(
            "No se pudo finalizar la entrega del folio %s: %s",
            clean_folio,
            error,
        )
        return False
    finally:
        if conn is not None:
            conn.close()


def mark_report_status_delivered(
    storage,
    folio: Any,
    claim_token: str,
    *,
    provider_message_id: Any = None,
    now: float | None = None,
) -> bool:
    return _finish_claim(
        storage,
        folio,
        claim_token,
        state="delivered",
        provider_message_id=provider_message_id,
        now=now,
    )


def mark_report_status_failed(
    storage,
    folio: Any,
    claim_token: str,
    *,
    ambiguous: bool = False,
    now: float | None = None,
) -> bool:
    # An ambiguous network result is intentionally terminal for the same
    # transition: retrying could duplicate a message Chat2Desk already sent.
    return _finish_claim(
        storage,
        folio,
        claim_token,
        state="ambiguous" if ambiguous else "failed",
        now=now,
    )


def clear_report_status_delivery_memory(folio: Any | None = None) -> None:
    """Test/support helper; durable rows are deliberately not deleted."""
    with _memory_lock:
        if folio is None:
            _memory_rows.clear()
        else:
            clean_folio = _clean(folio)
            if clean_folio:
                _memory_rows.pop(clean_folio, None)
