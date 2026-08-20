import os
import asyncio
import re
from collections import Counter
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from app.util.database import LocalStorage
from app.util.logger import logger


AUDIT_INTERVAL_HOURS = int(os.environ.get("OPERATIONAL_AUDIT_INTERVAL_HOURS", "12"))
AUDIT_OUTPUT_DIR = Path(os.environ.get("OPERATIONAL_AUDIT_OUTPUT_DIR", "operational_reports"))
AUDIT_LOG_SAMPLE_LIMIT = int(os.environ.get("OPERATIONAL_AUDIT_LOG_SAMPLE_LIMIT", "12"))
AUDIT_MESSAGE_SAMPLE_LIMIT = int(os.environ.get("OPERATIONAL_AUDIT_MESSAGE_SAMPLE_LIMIT", "8"))
AUDIT_RETENTION_DAYS = int(os.environ.get("OPERATIONAL_AUDIT_RETENTION_DAYS", "3"))

LOG_PATTERNS = {
    "llm_failure": ["[LLM FAILURE]", "Error al generar la respuesta"],
    "openai_timeout": ["ConnectTimeout", "APITimeoutError", "[OPENAI REQUEST FAILURE]"],
    "outbound_error": ["Error en respuesta Chat2Desk", "Error al enviar mensaje", "[CHAT2DESK:whatsapp_main]"],
    "dedup": ["[PERSISTED DUPLICATE]", "[OUTBOUND DEDUP]", "[STALE INBOUND]"],
    "human_takeover": ["Human agent takeover detected", "Deteccion automatica: Agente humano"],
}

PHONE_PATTERN = re.compile(r"(?:from_number=|for |from )(?P<phone>52\d{10,13})")
UID_PATTERN = re.compile(r"uid=(?P<uid>[A-Za-z0-9._:-]+)")


def _connect(storage: LocalStorage):
    return psycopg2.connect(
        dbname=storage.dbName,
        user=storage.user,
        password=storage.password,
        host=storage.host,
        port=storage.port,
    )


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _load_db_metrics(storage: LocalStorage, since: datetime) -> dict:
    metrics = {
        "message_totals": {},
        "top_numbers": [],
        "latest_inbound": [],
        "latest_outbound": [],
        "likely_unanswered_inbound": [],
        "silence_breakdown": {},
        "silence_breakdown_samples": {},
    }

    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    with _connect(storage) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT direction, COUNT(*) AS total
                FROM messages
                WHERE source = 'whatsapp' AND time >= %s
                GROUP BY direction
                """,
                [since_str],
            )
            metrics["message_totals"] = {
                row["direction"]: _safe_int(row["total"]) for row in cursor.fetchall()
            }

            cursor.execute(
                """
                SELECT COUNT(DISTINCT number) AS total
                FROM messages
                WHERE source = 'whatsapp' AND time >= %s
                """,
                [since_str],
            )
            row = cursor.fetchone() or {}
            metrics["unique_numbers"] = _safe_int(row.get("total"))

            cursor.execute(
                """
                SELECT number, COUNT(*) AS total
                FROM messages
                WHERE source = 'whatsapp' AND time >= %s
                GROUP BY number
                ORDER BY total DESC
                LIMIT 10
                """,
                [since_str],
            )
            metrics["top_numbers"] = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT time, number, message
                FROM messages
                WHERE source = 'whatsapp' AND direction = 'inbound' AND time >= %s
                ORDER BY id DESC
                LIMIT %s
                """,
                [since_str, AUDIT_MESSAGE_SAMPLE_LIMIT],
            )
            metrics["latest_inbound"] = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT time, number, message
                FROM messages
                WHERE source = 'whatsapp' AND direction = 'outbound' AND time >= %s
                ORDER BY id DESC
                LIMIT %s
                """,
                [since_str, AUDIT_MESSAGE_SAMPLE_LIMIT],
            )
            metrics["latest_outbound"] = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT m1.time, m1.number, m1.uid, m1.message
                FROM messages m1
                WHERE
                    m1.source = 'whatsapp'
                    AND m1.direction = 'inbound'
                    AND m1.time >= %s
                    AND NOT EXISTS (
                        SELECT 1
                        FROM messages m2
                        WHERE
                            m2.source = 'whatsapp'
                            AND m2.direction = 'outbound'
                            AND m2.number = m1.number
                            AND to_timestamp(m2.time, 'YYYY-MM-DD HH24:MI:SS')
                                >= to_timestamp(m1.time, 'YYYY-MM-DD HH24:MI:SS')
                            AND to_timestamp(m2.time, 'YYYY-MM-DD HH24:MI:SS')
                                <= to_timestamp(m1.time, 'YYYY-MM-DD HH24:MI:SS') + interval '10 minutes'
                    )
                ORDER BY m1.id DESC
                LIMIT %s
                """,
                [since_str, AUDIT_MESSAGE_SAMPLE_LIMIT],
            )
            metrics["likely_unanswered_inbound"] = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM messages m1
                WHERE
                    m1.source = 'whatsapp'
                    AND m1.direction = 'inbound'
                    AND m1.time >= %s
                    AND NOT EXISTS (
                        SELECT 1
                        FROM messages m2
                        WHERE
                            m2.source = 'whatsapp'
                            AND m2.direction = 'outbound'
                            AND m2.number = m1.number
                            AND to_timestamp(m2.time, 'YYYY-MM-DD HH24:MI:SS')
                                >= to_timestamp(m1.time, 'YYYY-MM-DD HH24:MI:SS')
                            AND to_timestamp(m2.time, 'YYYY-MM-DD HH24:MI:SS')
                                <= to_timestamp(m1.time, 'YYYY-MM-DD HH24:MI:SS') + interval '10 minutes'
                    )
                """,
                [since_str],
            )
            unanswered_row = cursor.fetchone() or {}
            metrics["likely_unanswered_inbound_total"] = _safe_int(unanswered_row.get("total"))

    return metrics


def _truncate(text: str | None, limit: int = 160) -> str:
    if not text:
        return ""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def _iter_audit_report_paths() -> list[Path]:
    if not AUDIT_OUTPUT_DIR.exists():
        return []
    return sorted(
        [
            path for path in AUDIT_OUTPUT_DIR.glob("sam_operational_audit_*.txt")
            if path.name != "sam_operational_audit_latest.txt"
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def cleanup_old_operational_audit_reports() -> list[str]:
    cutoff = datetime.now() - timedelta(days=AUDIT_RETENTION_DAYS)
    deleted: list[str] = []

    for path in _iter_audit_report_paths():
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at < cutoff:
            with suppress(Exception):
                path.unlink()
                deleted.append(path.name)

    return deleted


def list_operational_audit_reports(limit: int = 20) -> list[dict]:
    reports = []
    for path in _iter_audit_report_paths()[:limit]:
        stat = path.stat()
        reports.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return reports


def read_latest_operational_audit_report() -> dict | None:
    latest_path = AUDIT_OUTPUT_DIR / "sam_operational_audit_latest.txt"
    if not latest_path.exists():
        return None

    stat = latest_path.stat()
    return {
        "name": latest_path.name,
        "path": str(latest_path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "content": latest_path.read_text(encoding="utf-8", errors="ignore"),
    }


def _read_recent_log_signals() -> dict:
    result = {
        "enabled": False,
        "path": None,
        "counts": Counter(),
        "samples": {key: [] for key in LOG_PATTERNS},
        "error_lines": [],
    }

    if os.environ.get("LOG_TO_FILE", "").lower() != "true":
        return result

    log_path = Path(os.environ.get("LOG_FILE", "log_file.log"))
    result["enabled"] = True
    result["path"] = str(log_path)

    if not log_path.exists():
        return result

    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()[-4000:]
    except Exception as exc:
        logger.error("[AUDIT] No se pudo leer log file %s: %s", log_path, exc)
        return result

    behavior = _analyze_behavioral_patterns(lines)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if " - ERROR - " in line:
            result["counts"]["error"] += 1
            if len(result["error_lines"]) < AUDIT_LOG_SAMPLE_LIMIT:
                result["error_lines"].append(line)

        if " - CRITICAL - " in line:
            result["counts"]["critical"] += 1

        for key, patterns in LOG_PATTERNS.items():
            if any(pattern in line for pattern in patterns):
                result["counts"][key] += 1
                if len(result["samples"][key]) < AUDIT_LOG_SAMPLE_LIMIT:
                    result["samples"][key].append(line)

    result["behavior"] = behavior
    result["raw_lines"] = lines
    return result


def _extract_phone(line: str) -> str | None:
    match = PHONE_PATTERN.search(line)
    if match:
        return match.group("phone")
    return None


def _extract_uid(line: str) -> str | None:
    match = UID_PATTERN.search(line)
    if match:
        return match.group("uid")
    return None


def _analyze_behavioral_patterns(lines: list[str]) -> dict:
    behavior = {
        "human_takeover_count": 0,
        "return_to_bot_count": 0,
        "ignored_while_human_count": 0,
        "possible_bot_intrusion_count": 0,
        "possible_bot_intrusion_samples": [],
        "ignored_while_human_samples": [],
    }

    human_active_numbers: set[str] = set()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        phone = _extract_phone(line)

        if "Human agent takeover detected for " in line or "Detección automática: Agente humano" in line:
            behavior["human_takeover_count"] += 1
            if phone:
                human_active_numbers.add(phone)
            continue

        if "Control released to AI for next inbound message" in line or "human_goodbye_release" in line:
            behavior["return_to_bot_count"] += 1
            if phone and phone in human_active_numbers:
                human_active_numbers.discard(phone)
            continue

        if "Ignoring message from " in line and "being handled by a human agent" in line:
            behavior["ignored_while_human_count"] += 1
            if len(behavior["ignored_while_human_samples"]) < AUDIT_LOG_SAMPLE_LIMIT:
                behavior["ignored_while_human_samples"].append(line)
            if phone:
                human_active_numbers.add(phone)
            continue

        if "📤 [CHAT2DESK:whatsapp_main] attempt" in line and phone and phone in human_active_numbers:
            behavior["possible_bot_intrusion_count"] += 1
            if len(behavior["possible_bot_intrusion_samples"]) < AUDIT_LOG_SAMPLE_LIMIT:
                behavior["possible_bot_intrusion_samples"].append(line)

    return behavior


def _classify_silence_candidates(metrics: dict, log_signals: dict) -> None:
    candidates = metrics.get("likely_unanswered_inbound") or []
    buckets = {
        "human_takeover_ignored": [],
        "deduplicated_or_redelivered": [],
        "llm_or_network_failure": [],
        "unclassified": [],
    }

    lines = log_signals.get("raw_lines") or []
    by_uid: dict[str, list[str]] = {}
    by_phone: dict[str, list[str]] = {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        uid = _extract_uid(line)
        phone = _extract_phone(line)
        if uid:
            by_uid.setdefault(uid, []).append(line)
        if phone:
            by_phone.setdefault(phone, []).append(line)

    for row in candidates:
        uid = str(row.get("uid") or "")
        phone = str(row.get("number") or "")
        related_lines: list[str] = []

        if uid and uid in by_uid:
            related_lines.extend(by_uid[uid])
        if phone and phone in by_phone:
            related_lines.extend(by_phone[phone][-40:])

        seen = set()
        unique_lines = []
        for line in related_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        if any("being handled by a human agent" in line for line in unique_lines):
            bucket = "human_takeover_ignored"
        elif any(
            marker in line
            for line in unique_lines
            for marker in ("[PERSISTED DUPLICATE]", "[STALE INBOUND]", "persisted_duplicate_inbound_ignored")
        ):
            bucket = "deduplicated_or_redelivered"
        elif any(
            marker in line
            for line in unique_lines
            for marker in ("[LLM FAILURE]", "ConnectTimeout", "APITimeoutError", "[OPENAI REQUEST FAILURE]", "Error al generar la respuesta")
        ):
            bucket = "llm_or_network_failure"
        else:
            bucket = "unclassified"

        buckets[bucket].append(
            {
                "time": row.get("time"),
                "number": phone,
                "uid": uid,
                "message": row.get("message"),
            }
        )

    metrics["silence_breakdown"] = {key: len(value) for key, value in buckets.items()}
    metrics["silence_breakdown_samples"] = {
        key: value[:AUDIT_MESSAGE_SAMPLE_LIMIT] for key, value in buckets.items()
    }


def _build_findings(metrics: dict, log_signals: dict) -> list[str]:
    findings = []

    inbound_total = _safe_int(metrics.get("message_totals", {}).get("inbound"))
    outbound_total = _safe_int(metrics.get("message_totals", {}).get("outbound"))
    unique_numbers = _safe_int(metrics.get("unique_numbers"))

    findings.append(
        f"Actividad whatsapp ultimas {AUDIT_INTERVAL_HOURS}h: inbound={inbound_total}, outbound={outbound_total}, usuarios_unicos={unique_numbers}"
    )

    if inbound_total > 0 and outbound_total == 0:
        findings.append("ALERTA: hubo mensajes inbound pero cero respuestas outbound.")
    elif inbound_total > outbound_total * 2 and inbound_total >= 10:
        findings.append("ALERTA: el volumen inbound supera por mucho al outbound; revisar caidas o conversaciones atascadas.")

    if log_signals["counts"].get("openai_timeout", 0) > 0:
        findings.append(
            f"ALERTA: se detectaron {log_signals['counts'].get('openai_timeout', 0)} eventos de timeout/conectividad hacia OpenAI."
        )

    if log_signals["counts"].get("llm_failure", 0) > 0:
        findings.append(
            f"ALERTA: se detectaron {log_signals['counts'].get('llm_failure', 0)} fallas de LLM en logs."
        )

    if log_signals["counts"].get("outbound_error", 0) > 0:
        findings.append(
            f"ALERTA: se detectaron {log_signals['counts'].get('outbound_error', 0)} eventos ligados a envio/salida Chat2Desk."
        )

    if log_signals["counts"].get("dedup", 0) > 0:
        findings.append(
            f"Observacion: hubo {log_signals['counts'].get('dedup', 0)} eventos de deduplicacion. Validar si corresponden a reentregas normales."
        )

    unanswered_total = _safe_int(metrics.get("likely_unanswered_inbound_total"))
    silence_breakdown = metrics.get("silence_breakdown") or {}
    if unanswered_total > 0:
        findings.append(
            f"ALERTA: se detectaron {unanswered_total} inbound sin outbound visible dentro de 10 minutos; posible feedback de 'a veces no contesta'."
        )
        if _safe_int(silence_breakdown.get("human_takeover_ignored")) > 0:
            findings.append(
                f"Desglose silencios: {silence_breakdown.get('human_takeover_ignored')} parecen explicarse por takeover humano activo."
            )
        if _safe_int(silence_breakdown.get("deduplicated_or_redelivered")) > 0:
            findings.append(
                f"Desglose silencios: {silence_breakdown.get('deduplicated_or_redelivered')} parecen ser duplicados o reentregas bloqueadas."
            )
        if _safe_int(silence_breakdown.get("llm_or_network_failure")) > 0:
            findings.append(
                f"Desglose silencios: {silence_breakdown.get('llm_or_network_failure')} coinciden con fallas de LLM/red."
            )
        if _safe_int(silence_breakdown.get("unclassified")) > 0:
            findings.append(
                f"Desglose silencios: {silence_breakdown.get('unclassified')} quedan sin clasificar y merecen revision manual."
            )

    behavior = log_signals.get("behavior") or {}
    if behavior.get("possible_bot_intrusion_count", 0) > 0:
        findings.append(
            f"ALERTA: se detectaron {behavior.get('possible_bot_intrusion_count', 0)} posibles respuestas del bot mientras la conversacion seguia marcada como humana."
        )
    if behavior.get("ignored_while_human_count", 0) > 0:
        findings.append(
            f"Observacion: hubo {behavior.get('ignored_while_human_count', 0)} inbound ignorados por takeover humano activo."
        )

    top_numbers = metrics.get("top_numbers") or []
    if top_numbers:
        top = top_numbers[0]
        findings.append(
            f"Numero con mayor actividad: {top.get('number')} con {top.get('total')} mensajes en la ventana."
        )

    return findings


def _render_report(metrics: dict, log_signals: dict, generated_at: datetime, since: datetime) -> str:
    _classify_silence_candidates(metrics, log_signals)
    findings = _build_findings(metrics, log_signals)
    lines: list[str] = []
    lines.append("SAM OPERATIONAL AUDIT")
    lines.append(f"generated_at: {generated_at.isoformat()}")
    lines.append(f"window_start: {since.isoformat()}")
    lines.append(f"window_hours: {AUDIT_INTERVAL_HOURS}")
    lines.append("")
    lines.append("RESUMEN")
    for finding in findings:
        lines.append(f"- {finding}")

    lines.append("")
    lines.append("METRICAS")
    lines.append(f"- inbound: {_safe_int(metrics.get('message_totals', {}).get('inbound'))}")
    lines.append(f"- outbound: {_safe_int(metrics.get('message_totals', {}).get('outbound'))}")
    lines.append(f"- system: {_safe_int(metrics.get('message_totals', {}).get('system'))}")
    lines.append(f"- unique_numbers: {_safe_int(metrics.get('unique_numbers'))}")

    lines.append("")
    lines.append("TOP NUMBERS")
    for row in metrics.get("top_numbers", []):
        lines.append(f"- {row.get('number')}: {row.get('total')} mensajes")
    if not metrics.get("top_numbers"):
        lines.append("- sin actividad en la ventana")

    lines.append("")
    lines.append("ULTIMOS INBOUND")
    for row in metrics.get("latest_inbound", []):
        lines.append(f"- [{row.get('time')}] {row.get('number')}: {_truncate(row.get('message'))}")
    if not metrics.get("latest_inbound"):
        lines.append("- sin mensajes inbound recientes")

    lines.append("")
    lines.append("ULTIMOS OUTBOUND")
    for row in metrics.get("latest_outbound", []):
        lines.append(f"- [{row.get('time')}] {row.get('number')}: {_truncate(row.get('message'))}")
    if not metrics.get("latest_outbound"):
        lines.append("- sin mensajes outbound recientes")

    lines.append("")
    lines.append("POSIBLES SILENCIOS")
    lines.append(f"- total_likely_unanswered_inbound: {_safe_int(metrics.get('likely_unanswered_inbound_total'))}")
    silence_breakdown = metrics.get("silence_breakdown") or {}
    lines.append(f"- human_takeover_ignored: {_safe_int(silence_breakdown.get('human_takeover_ignored'))}")
    lines.append(f"- deduplicated_or_redelivered: {_safe_int(silence_breakdown.get('deduplicated_or_redelivered'))}")
    lines.append(f"- llm_or_network_failure: {_safe_int(silence_breakdown.get('llm_or_network_failure'))}")
    lines.append(f"- unclassified: {_safe_int(silence_breakdown.get('unclassified'))}")
    for row in metrics.get("likely_unanswered_inbound", []):
        lines.append(f"- [{row.get('time')}] {row.get('number')} uid={row.get('uid')}: {_truncate(row.get('message'))}")
    if not metrics.get("likely_unanswered_inbound"):
        lines.append("- sin muestras de inbound aparentemente no contestado")

    lines.append("")
    lines.append("SILENCE BREAKDOWN SAMPLES")
    for bucket_name, samples in (metrics.get("silence_breakdown_samples") or {}).items():
        lines.append(bucket_name.upper())
        if samples:
            for sample in samples:
                lines.append(
                    f"- [{sample.get('time')}] {sample.get('number')} uid={sample.get('uid')}: {_truncate(sample.get('message'))}"
                )
        else:
            lines.append("- sin muestras")

    lines.append("")
    lines.append("LOG SIGNALS")
    if not log_signals.get("enabled"):
        lines.append("- LOG_TO_FILE no esta activo; no se pudo inspeccionar archivo de logs.")
    else:
        lines.append(f"- log_file: {log_signals.get('path')}")
        lines.append(f"- error_lines: {log_signals['counts'].get('error', 0)}")
        lines.append(f"- critical_lines: {log_signals['counts'].get('critical', 0)}")
        for key in LOG_PATTERNS:
            lines.append(f"- {key}: {log_signals['counts'].get(key, 0)}")

        behavior = log_signals.get("behavior") or {}
        lines.append(f"- human_takeover_count: {behavior.get('human_takeover_count', 0)}")
        lines.append(f"- return_to_bot_count: {behavior.get('return_to_bot_count', 0)}")
        lines.append(f"- ignored_while_human_count: {behavior.get('ignored_while_human_count', 0)}")
        lines.append(f"- possible_bot_intrusion_count: {behavior.get('possible_bot_intrusion_count', 0)}")

        for key, samples in log_signals.get("samples", {}).items():
            lines.append("")
            lines.append(f"LOG SAMPLES {key.upper()}")
            if samples:
                for sample in samples:
                    lines.append(f"- {_truncate(sample, 260)}")
            else:
                lines.append("- sin muestras")

        lines.append("")
        lines.append("LOG ERROR SAMPLES")
        if log_signals.get("error_lines"):
            for sample in log_signals["error_lines"]:
                lines.append(f"- {_truncate(sample, 260)}")
        else:
            lines.append("- sin muestras")

        lines.append("")
        lines.append("BEHAVIORAL SAMPLES")
        behavior = log_signals.get("behavior") or {}
        lines.append("POSSIBLE BOT INTRUSION")
        if behavior.get("possible_bot_intrusion_samples"):
            for sample in behavior["possible_bot_intrusion_samples"]:
                lines.append(f"- {_truncate(sample, 260)}")
        else:
            lines.append("- sin muestras")

        lines.append("IGNORED WHILE HUMAN")
        if behavior.get("ignored_while_human_samples"):
            for sample in behavior["ignored_while_human_samples"]:
                lines.append(f"- {_truncate(sample, 260)}")
        else:
            lines.append("- sin muestras")

    lines.append("")
    lines.append("RECOMENDACIONES")
    lines.append("- revisar cualquier patron repetido de ConnectTimeout, APITimeoutError o LLM FAILURE")
    lines.append("- comparar inbound vs outbound; una brecha alta suele indicar caidas o bloqueos operativos")
    lines.append("- revisar numeros con actividad anormalmente alta para detectar loops, retries o conversaciones atoradas")

    return "\n".join(lines) + "\n"


def generate_operational_audit_report() -> Path:
    storage = LocalStorage()
    generated_at = datetime.now()
    since = generated_at - timedelta(hours=AUDIT_INTERVAL_HOURS)
    metrics = _load_db_metrics(storage, since)
    log_signals = _read_recent_log_signals()
    report_body = _render_report(metrics, log_signals, generated_at, since)

    AUDIT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    report_path = AUDIT_OUTPUT_DIR / f"sam_operational_audit_{timestamp}.txt"
    latest_path = AUDIT_OUTPUT_DIR / "sam_operational_audit_latest.txt"

    report_path.write_text(report_body, encoding="utf-8")
    latest_path.write_text(report_body, encoding="utf-8")
    deleted_reports = cleanup_old_operational_audit_reports()

    logger.info("[AUDIT] Reporte operativo generado en %s", report_path)
    if deleted_reports:
        logger.info("[AUDIT] Reportes viejos eliminados por retencion: %s", deleted_reports)
    return report_path


async def operational_audit_scheduler():
    logger.info(
        "[AUDIT] Scheduler operativo iniciado. interval_hours=%s output_dir=%s",
        AUDIT_INTERVAL_HOURS,
        AUDIT_OUTPUT_DIR,
    )

    while True:
        try:
            report_path = generate_operational_audit_report()
            logger.info("[AUDIT] Resumen operativo actualizado: %s", report_path)
        except Exception as exc:
            logger.exception("[AUDIT] Error generando reporte operativo: %s", exc)

        try:
            await asyncio.sleep(AUDIT_INTERVAL_HOURS * 60 * 60)
        except asyncio.CancelledError:
            logger.info("[AUDIT] Scheduler operativo cancelado")
            raise
