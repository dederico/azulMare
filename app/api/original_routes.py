import re
import unicodedata
import hashlib
import httpx
import requests
import json
import html
from datetime import datetime
import traceback
import base64
import aiohttp
import logging
import urllib.parse
import os
import json
from io import StringIO
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytz
from io import BytesIO
import requests
import openai
from openai import OpenAI
import asyncio
from contextlib import asynccontextmanager
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.util.database import LocalStorage
from app.models.Config import Config
from app.models.Message import Message
from app.models.OutgoingCampaign import OutgoingCampaign
from app.models.OutgoingRecipient import OutgoingRecipient
# from app.services.llm.deepseek_service import DeepSeekService  # Not used
from app.services.llm.openai_service import OpenAIService
from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions
from app.util.logger import logger
from datetime import datetime
import pytz
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
import traceback
from app.services.llm.llm_service import LLMService
import psycopg2
from collections import OrderedDict
from datetime import datetime, timedelta


load_dotenv(override=True)
from fastapi import APIRouter, Request, Response, WebSocket, HTTPException, FastAPI
from twilio.twiml.voice_response import VoiceResponse, Connect
from app.api.websocket_handler import WebSocketHandler
from app.core.orchestrator import Orchestrator
# from app.services.stt.deepgram_service import DeepgramService  # Not used
from app.services.stt.amazon_service import AmazonTranscribeService
# from app.services.tts.eleven_service import ElevenTTSService  # Not used
from app.services.tts.polly_service import AmazonTTSService
from app.services.functions.function_registry import registered_functions
from app.services.llm.config.system import system_message
from app.services.functions.function_manager import FunctionManager
from app.services.functions.implementations.geocoding import latlong_to_address
from app.services.functions.implementations.nearest_office import find_nearest_government_office
from app.util.rate_limiter import image_processing_queue


from twilio.rest import Client
from urllib.parse import parse_qs
from datetime import datetime
from copy import deepcopy
from app.util.logger import logger, get_thread_log_handler, cleanup_call_logger
from app.models.Call import Call
from app.models.Message import Message
from app.models.Config import Config
from app.util.factory import Hooks
from app.util.database import LocalStorage
from app.services.functions.implementations.save_selection2 import save_client_selection2
from app.services.functions.implementations.save_selection import find_row_and_update_selection
from app.services.functions.implementations.identify import get_customer_identity
from app.services.functions.implementations.date import get_current_date
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from app.services.stt.stt_service import STTService
from app.services.stt.media_transcriber import TranscribeOGG
from twilio.base.exceptions import TwilioRestException
import threading
from app.services.functions.implementations.transfer_message_event import transfer_to_group
from threading import RLock
from app.api.streets_array import SAN_PEDRO_STREETS_REAL
from app.api.colonies_array import SAN_PEDRO_COLONIES
import difflib
import re
from app.services.deduplication import dedup_manager, dedup_cleanup_task
from app.services.monitoring.operational_audit import (
    read_latest_operational_audit_report,
    list_operational_audit_reports,
    generate_operational_audit_snapshot,
)

#from app.services.functions.implementations.save_selection2 import save_user_answer, get_user_answer
evaluated_reports = {}
# ===============================================
# 🆕 SISTEMA DE EVALUACIÓN POST-RESOLUCIÓN
# ===============================================


def _truncate_for_log(value, limit=500):
    if value is None:
        return None
    value = str(value)
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated {len(value) - limit} chars]"


def parse_chat2desk_event_timestamp(event_time: str | None) -> float | None:
    if not event_time:
        return None

    try:
        return datetime.fromisoformat(event_time.replace("Z", "+00:00")).timestamp()
    except Exception:
        logger.warning("⚠️ [EVENT TIME] No se pudo parsear event_time=%s", event_time)
        return None


def has_persisted_whatsapp_message_uid(db, uid) -> bool:
    if uid in (None, ""):
        return False

    try:
        existing_message = db.Search(
            Message(uid=str(uid), source="whatsapp"),
            single=True,
        )
        return existing_message is not None
    except Exception as e:
        logger.error("Error consultando deduplicación persistente para uid=%s: %s", uid, str(e))
        return False


def build_successful_delivery_marker_uid(uid) -> str:
    return f"delivered-inbound-{uid}"


def has_successful_delivery_marker_for_inbound_uid(db, uid) -> bool:
    if uid in (None, ""):
        return False

    try:
        delivery_marker = db.Search(
            Message(uid=build_successful_delivery_marker_uid(uid), source="whatsapp"),
            single=True,
        )
        return delivery_marker is not None
    except Exception as e:
        logger.error("Error consultando marker de entrega para uid=%s: %s", uid, str(e))
        return False


def persist_successful_delivery_marker(db, from_number: str, uid, message_id) -> None:
    if uid in (None, ""):
        return

    marker_uid = build_successful_delivery_marker_uid(uid)
    if has_successful_delivery_marker_for_inbound_uid(db, uid):
        return

    marker = Message(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        senderName="System",
        message=f"[SYSTEM] Successful outbound delivery confirmed for inbound uid={uid} message_id={message_id}",
        number=from_number,
        uid=marker_uid,
        direction="system",
        mtype="text",
        source="whatsapp",
    )
    db.Insert(marker)


def format_event_timestamp_for_log(timestamp: float | None) -> str:
    if timestamp is None:
        return "None"
    return datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC")).isoformat()


def normalize_operator_message_text(text: str | None) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def is_human_takeover_message(text: str | None) -> bool:
    normalized = normalize_operator_message_text(text)
    return (
        "buen dia" in normalized
        and "atencion ciudadana" in normalized
        and "le atiende" in normalized
    )


def is_bot_return_message(text: str | None) -> bool:
    normalized = normalize_operator_message_text(text)
    return (
        "gracias por comunicarse" in normalized
        and "atencion ciudadana" in normalized
        and "reiniciar el chatbot" in normalized
        and "sam" in normalized
    )


def log_chat2desk_outbound_attempt(context, payload, from_number=None, message_id=None):
    safe_payload = dict(payload or {})
    if "text" in safe_payload:
        safe_payload["text_preview"] = _truncate_for_log(safe_payload.get("text"), 300)
        safe_payload["text_length"] = len(safe_payload.get("text") or "")
        del safe_payload["text"]

    logger.critical(
        f"📤 [CHAT2DESK:{context}] attempt "
        f"from_number={from_number} message_id={message_id} payload={json.dumps(safe_payload, ensure_ascii=False)}"
    )


def log_chat2desk_outbound_response(context, response, from_number=None, message_id=None):
    body_preview = _truncate_for_log(getattr(response, "text", None), 500)
    logger.critical(
        f"📥 [CHAT2DESK:{context}] response "
        f"from_number={from_number} message_id={message_id} "
        f"status_code={getattr(response, 'status_code', 'unknown')} body={body_preview}"
    )


def _normalize_campaign_phone(raw_phone: str) -> str:
    digits = "".join(ch for ch in (raw_phone or "") if ch.isdigit())
    if len(digits) == 10:
        return f"+52{digits}"
    if len(digits) == 12 and digits.startswith("52"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("521"):
        return f"+52{digits[3:]}"
    if raw_phone and raw_phone.strip().startswith("+"):
        return "+" + digits
    return f"+{digits}" if digits else ""


def _resolve_campaign_delivery_status(recipients) -> str:
    if not recipients:
        return "failed"

    sent_count = sum(1 for recipient in recipients if (getattr(recipient, "status", "") or "").lower() == "sent")
    failed_count = sum(1 for recipient in recipients if (getattr(recipient, "status", "") or "").lower() == "failed")
    pending_count = sum(1 for recipient in recipients if (getattr(recipient, "status", "pending") or "pending").lower() == "pending")

    if pending_count > 0:
        return "processing"
    if sent_count > 0 and failed_count > 0:
        return "completed_with_errors"
    if sent_count > 0:
        return "completed"
    return "failed"


def _classify_outgoing_system_error(text: str) -> tuple[str, str]:
    message = (text or "").strip()
    lowered = message.lower()
    if " read " in f" {lowered} " or " leído" in lowered or " leido" in lowered or "seen" in lowered or "visto" in lowered:
        return "WHATSAPP_READ", "chat2desk_read"
    if "24 hours passed" in lowered or "approved whatsapp templates" in lowered:
        return "WHATSAPP_WINDOW_24H", "whatsapp_system"
    if "template" in lowered:
        return "WHATSAPP_TEMPLATE_REQUIRED", "whatsapp_system"
    return "WHATSAPP_SYSTEM", "whatsapp_system"


def _list_ranked_campaign_recipients_for_phone(db: LocalStorage, normalized_phone: str):
    recipients = db.Search(OutgoingRecipient(phone=normalized_phone), order="desc") or []
    return sorted(
        recipients,
        key=lambda recipient: (
            getattr(recipient, "returnToSamSentAt", "") or "",
            getattr(recipient, "freeMessageSentAt", "") or "",
            getattr(recipient, "hookSentAt", "") or "",
            getattr(recipient, "sentAt", "") or "",
            getattr(recipient, "lastAttemptAt", "") or "",
            getattr(recipient, "id", 0),
        ),
        reverse=True,
    )


def _get_latest_campaign_recipient_for_phone(db: LocalStorage, normalized_phone: str):
    ranked = _list_ranked_campaign_recipients_for_phone(db, normalized_phone)
    for recipient in ranked:
        status = (getattr(recipient, "status", "") or "").lower()
        if status == "sent":
            return recipient
    return None


def _get_latest_relevant_campaign_recipient_for_phone(db: LocalStorage, normalized_phone: str):
    ranked = _list_ranked_campaign_recipients_for_phone(db, normalized_phone)
    for recipient in ranked:
        status = (getattr(recipient, "status", "") or "").lower()
        if status in {"sent", "processing", "pending"}:
            return recipient
    return ranked[0] if ranked else None


def _is_proactive_campaign_guard_active(campaign, recipient) -> bool:
    campaign_kind = (getattr(campaign, "campaignKind", "") or "").strip().lower()
    if campaign_kind in {"hsm_hook", "free_followup"}:
        return True
    if campaign_kind != "hsm_sequence":
        return False

    return_to_sam_enabled = bool(getattr(campaign, "returnToSamEnabled", False))
    if return_to_sam_enabled:
        return not bool(getattr(recipient, "returnToSamSentAt", "") or "")
    return not bool(getattr(recipient, "freeMessageSentAt", "") or "")


def get_active_proactive_campaign_guard(db: LocalStorage, raw_phone: str) -> dict | None:
    normalized_phone = _normalize_campaign_phone(raw_phone)
    if not normalized_phone:
        return None

    latest_recipient = _get_latest_relevant_campaign_recipient_for_phone(db, normalized_phone)
    if not latest_recipient:
        return None

    campaign = db.GetByPK(OutgoingCampaign, latest_recipient.campaign_id)
    if not campaign:
        return None

    campaign_kind = (getattr(campaign, "campaignKind", "") or "").strip().lower()
    if campaign_kind not in {"hsm_hook", "free_followup", "hsm_sequence"}:
        return None

    if not _is_proactive_campaign_guard_active(campaign, latest_recipient):
        return None

    return {
        "campaign_id": getattr(campaign, "id", None),
        "campaign_name": getattr(campaign, "name", ""),
        "campaign_kind": campaign_kind,
        "phone": normalized_phone,
        "sent_at": getattr(latest_recipient, "sentAt", "") or getattr(latest_recipient, "lastAttemptAt", ""),
    }


def record_outgoing_campaign_reply(db: LocalStorage, raw_phone: str, reply_text: str) -> bool:
    normalized_phone = _normalize_campaign_phone(raw_phone)
    if not normalized_phone:
        return False

    recipient = _get_latest_relevant_campaign_recipient_for_phone(db, normalized_phone)
    if not recipient:
        return False

    campaign = db.GetByPK(OutgoingCampaign, recipient.campaign_id)
    if not campaign:
        return False

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = False
    if not getattr(recipient, "seenAt", ""):
        recipient.seenAt = now
        updated = True
    if not getattr(recipient, "repliedAt", ""):
        recipient.repliedAt = now
        updated = True
    cleaned_reply = (reply_text or "").strip()
    if cleaned_reply:
        recipient.replyText = _truncate_for_log(cleaned_reply, 500)
        updated = True
    if updated:
        db.Update(recipient)
        campaign.lastRunAt = now
        db.Update(campaign)
        logger.critical(
            "👀 [PROACTIVE REPLY] campaign_id=%s phone=%s kind=%s reply=%s",
            getattr(campaign, "id", "unknown"),
            normalized_phone,
            getattr(campaign, "campaignKind", ""),
            _truncate_for_log(cleaned_reply, 160),
        )
    return updated


def reconcile_outgoing_campaign_read_event(db: LocalStorage, payload: dict) -> bool:
    message_type = payload.get("type", "")
    hook_type = payload.get("hook_type", "")
    if hook_type != "outbox":
        return False

    system_text = payload.get("text", "") or ""
    lowered = system_text.lower()
    if message_type != "system" and not ("read" in lowered or "leído" in lowered or "leido" in lowered or "visto" in lowered):
        return False

    normalized_phone = _normalize_campaign_phone(payload.get("client", {}).get("phone", ""))
    if not normalized_phone:
        return False

    recipient = _get_latest_campaign_recipient_for_phone(db, normalized_phone)
    if not recipient:
        return False

    if getattr(recipient, "seenAt", ""):
        return True

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recipient.seenAt = now
    recipient.providerStatus = "chat2desk_read"
    recipient.providerPayload = json.dumps(payload, ensure_ascii=True)
    db.Update(recipient)
    logger.critical(
        "👁️ [PROACTIVE SEEN] campaign_id=%s phone=%s detail=%s",
        getattr(recipient, "campaign_id", "unknown"),
        normalized_phone,
        _truncate_for_log(system_text, 180),
    )
    return True


def reconcile_outgoing_campaign_outbox_event(db: LocalStorage, payload: dict) -> bool:
    message_type = payload.get("type", "")
    hook_type = payload.get("hook_type", "")
    if message_type != "to_client" or hook_type != "outbox":
        return False

    webhook_message_id = str(payload.get("message_id") or "")
    if not webhook_message_id:
        return False

    recipients = db.Search(OutgoingRecipient(providerMessageId=webhook_message_id), order="desc") or []
    if not recipients:
        return False

    target = recipients[0]
    target.status = "sent"
    target.providerStatus = "chat2desk_outbox"
    target.providerPayload = json.dumps(payload, ensure_ascii=True)
    target.lastAttemptAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not getattr(target, "sentAt", ""):
        target.sentAt = target.lastAttemptAt
    db.Update(target)

    campaign = db.GetByPK(OutgoingCampaign, target.campaign_id)
    if campaign:
        related = db.Search(OutgoingRecipient(campaign_id=campaign.id), order="asc") or []
        campaign.status = _resolve_campaign_delivery_status(related)
        campaign.lastRunAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.Update(campaign)

    logger.critical(
        "📬 [OUTGOING OUTBOX] campaign_id=%s phone=%s provider_message_id=%s request_id=%s channel_id=%s text=%s",
        getattr(target, "campaign_id", "unknown"),
        payload.get("client", {}).get("phone", ""),
        webhook_message_id,
        payload.get("request_id"),
        payload.get("channel_id"),
        _truncate_for_log(payload.get("text", ""), 240),
    )
    return True


def reconcile_outgoing_campaign_system_event(db: LocalStorage, payload: dict) -> bool:
    message_type = payload.get("type", "")
    hook_type = payload.get("hook_type", "")
    if message_type != "system" or hook_type != "outbox":
        return False

    client_phone = payload.get("client", {}).get("phone", "")
    normalized_phone = _normalize_campaign_phone(client_phone)
    if not normalized_phone:
        return False

    system_text = payload.get("text", "") or ""
    error_type, provider_status = _classify_outgoing_system_error(system_text)

    if error_type == "WHATSAPP_READ":
        return reconcile_outgoing_campaign_read_event(db, payload)

    recipients = db.Search(OutgoingRecipient(phone=normalized_phone), order="desc") or []
    if not recipients:
        logger.warning(f"📭 [OUTGOING SYSTEM] No se encontraron destinatarios de campaña para {normalized_phone}")
        return False

    target = None
    for recipient in recipients:
        status = (getattr(recipient, "status", "") or "").lower()
        if status in {"sent", "pending"}:
            target = recipient
            break

    if not target:
        logger.warning(f"📭 [OUTGOING SYSTEM] No hay destinatario elegible para actualizar con {normalized_phone}")
        return False

    target.status = "failed"
    target.errorType = error_type
    target.providerStatus = provider_status
    target.errorMessage = system_text.strip() or "WhatsApp rechazó el envío."
    target.providerPayload = json.dumps(payload, ensure_ascii=True)
    target.lastAttemptAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.Update(target)

    campaign = db.GetByPK(OutgoingCampaign, target.campaign_id)
    if campaign:
        related = db.Search(OutgoingRecipient(campaign_id=campaign.id), order="asc") or []
        campaign.status = _resolve_campaign_delivery_status(related)
        campaign.lastRunAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        campaign.lastError = target.errorMessage
        db.Update(campaign)

    logger.error(
        "📛 [OUTGOING SYSTEM] Campaña %s actualizada por rechazo real de WhatsApp para %s. type=%s detail=%s",
        getattr(target, "campaign_id", "unknown"),
        normalized_phone,
        error_type,
        target.errorMessage,
    )
    return True

# Estados de evaluación
EVALUATION_STATES = {
    "WAITING_OK_CLICK": "evaluacion_esperando_click_ok",  # 🆕 NUEVO
    "WAITING_RESOLUTION_RESPONSE": "evaluacion_esperando_respuesta_resolucion",
    "WAITING_RATING": "evaluacion_esperando_calificacion", 
    "WAITING_REASON": "evaluacion_esperando_motivo"
}

async def handle_hsm_conclusion_notification(payload, from_number):
    """
    Maneja notificaciones HSM de conclusión de reportes.
    SOLO GUARDA LA INFORMACIÓN, NO ENVÍA NADA AUTOMÁTICAMENTE.
    """
    
    # Verificar si es mensaje HSM de conclusión
    message_type = payload.get("type")
    text = payload.get("text", "")
    
    if message_type != "to_client" or not text.startswith("@HSM@"):
        return None
        
    # Parsear mensaje HSM
    hsm_parts = text.split("\n")
    if len(hsm_parts) < 5 or "notifica_conclusion" not in hsm_parts[1]:
        return None
        
    reporte_id = hsm_parts[3]
    client_id = payload.get("client", {}).get("id")
    channel_id = payload.get("channel_id")

    # 🆕 CLAVE ÚNICA MÁS ROBUSTA
    unique_key = f"{from_number}:{reporte_id}"

    # ✅ PREVENIR DUPLICADOS CON CLAVE ROBUSTA
    current_time = datetime.now().timestamp()
    if unique_key in hsm_sent_reports:
        elapsed = current_time - hsm_sent_reports[unique_key]
        if elapsed < 600:  # 10 minutos en lugar de 5
            logger.warning(f"🚫 [HSM DUPLICATE] HSM para {unique_key} ya procesado hace {elapsed:.1f}s")
            return {"status": True, "message": "HSM ya procesado", "reporte_id": reporte_id}
    
    # Marcar como procesado
    hsm_sent_reports[unique_key] = current_time
    
    logger.critical(f"🎯 [HSM RECEIVED] Reporte {reporte_id} listo para evaluación (esperando OK)")

    # ✅ SOLO GUARDAR INFORMACIÓN, NO ENVIAR NADA AÚN
    if from_number not in user_sessions:
        user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
    
    session = user_sessions[from_number]
    session.evaluation_state = EVALUATION_STATES["WAITING_OK_CLICK"]
    session.evaluation_folio = reporte_id
    session.last_hsm_time = current_time
    session.evaluation_client_id = client_id  # Guardar para uso posterior
    session.evaluation_channel_id = channel_id  # Guardar para uso posterior
    session.update_activity()
    
    logger.critical(f"✅ [HSM SAVED] Información guardada, esperando click de OK")
    
    return {
        "status": True,
        "message": "HSM recibido, esperando confirmación del usuario",
        "reporte_id": reporte_id
    }


async def handle_evaluation_response(from_number, text, client_id, channel_id, transport="wa_direct"):
    """
    Maneja respuestas del usuario durante el flujo de evaluación.

    Args:
        from_number: Número del usuario
        text: Texto de la respuesta
        client_id: ID del cliente en Chat2Desk
        channel_id: ID del canal
        transport: Transport type (wa_direct or widget)
        
    Returns:
        bool: True si se procesó como evaluación, False si no
    """
    # 🛡️ FILTRO: No procesar mensajes del bot
    if not text or len(text.strip()) == 0:
        return False
    
    # Detectar mensajes del bot (formato de conclusión)
    text_lower = text.lower()
    bot_indicators = [
        "reporte #", "concluido", "comentario de conclusión", 
        "ubicación atendida", "por favor responde"
    ]
    
    # Si contiene indicadores del bot, ignorar
    if any(indicator in text_lower for indicator in bot_indicators):
        logger.critical(f"🚫 [EVAL FILTER] Mensaje del bot ignorado: '{text[:30]}...'")
        return False
    
    if from_number not in user_sessions:
        logger.critical(f"❌ [EVAL] No hay sesión para {from_number}")
        return False
        
    session = user_sessions[from_number]
    evaluation_state = getattr(session, 'evaluation_state', None)
    
    if not evaluation_state:
        logger.critical(f"❌ [EVAL] No hay estado de evaluación para {from_number}")
        return False
    
    logger.critical(f"🎯 [EVAL] Procesando respuesta '{text}' en estado '{evaluation_state}'")
    normalized_text = text.strip()
    respuesta = normalized_text.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace(" ", "")

    # Compatibilidad con estados legacy guardados como clave simbólica.
    if evaluation_state == "WAITING_OK_CLICK":
        evaluation_state = EVALUATION_STATES["WAITING_OK_CLICK"]
        session.evaluation_state = evaluation_state
        session.update_activity()
    
    # ESTADO 0: Esperando confirmación OK para iniciar evaluación.
    if evaluation_state == EVALUATION_STATES["WAITING_OK_CLICK"]:
        logger.critical("🎯 [EVAL] Estado WAITING_OK_CLICK detectado")
        if respuesta != "ok":
            clarification_message = "Para continuar con la evaluación, por favor responde *OK*."
            await send_chat2desk_message_direct(client_id, channel_id, clarification_message, transport)
            return True

        folio = getattr(session, 'evaluation_folio', 'UNKNOWN')
        evaluation_client_id = getattr(session, 'evaluation_client_id', client_id)
        evaluation_channel_id = getattr(session, 'evaluation_channel_id', channel_id)

        session.evaluation_state = EVALUATION_STATES["WAITING_RESOLUTION_RESPONSE"]
        session.evaluation_client_id = evaluation_client_id
        session.evaluation_channel_id = evaluation_channel_id
        session.update_activity()

        try:
            await send_conclusion_comment_and_image(
                evaluation_client_id,
                evaluation_channel_id,
                folio,
                transport,
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"❌ [EVAL] Error enviando conclusión para folio {folio}: {str(e)}")

        validation_message = "¿Está de acuerdo con la resolución? Por favor responda *Sí* o *No*."
        await send_chat2desk_message_direct(
            evaluation_client_id,
            evaluation_channel_id,
            validation_message,
            transport,
        )
        logger.critical(f"✅ [EVAL] Evaluación activada para folio {folio} desde WAITING_OK_CLICK")
        return True
    
    # ESTADO 1: Esperando respuesta sobre resolución (Sí/No)
    if evaluation_state == EVALUATION_STATES["WAITING_RESOLUTION_RESPONSE"]:
        logger.critical(f"🎯 [EVAL] Esperando Sí/No, recibido: '{respuesta}'")
        
        if respuesta in ["si", "s", "sí"]:
            # Usuario está de acuerdo, pedir calificación
            session.evaluation_state = EVALUATION_STATES["WAITING_RATING"]
            session.update_activity()
            
            rating_message = """¿Qué te pareció la atención de tu reporte?
    1. 😒 Pésimo
    2. 😑 Malo  
    3. 🤔 Bien
    4. 😃 Muy bien
    5. 😍 Excelente

    Escribe el número de la opción que quieres seleccionar."""

            await send_chat2desk_message_direct(client_id, channel_id, rating_message, transport)
            logger.critical(f"✅ [EVALUACIÓN] Usuario {from_number} acordó con resolución")
            return True
            
        elif respuesta in ["no", "n"]:
            # Usuario no está de acuerdo, pedir motivo
            session.evaluation_state = EVALUATION_STATES["WAITING_REASON"]
            session.update_activity()
            
            reason_message = "¿Podrías indicarnos el motivo por el cuál no tuvo resolución?"
            await send_chat2desk_message_direct(client_id, channel_id, reason_message, transport)
            logger.critical(f"⚠️ [EVALUACIÓN] Usuario {from_number} NO acordó con resolución")
            return True
            
        else:
            # Respuesta inválida
            logger.critical(f"❌ [EVAL] Respuesta inválida para Sí/No: '{respuesta}'")
            clarification_message = "Por favor responde *Sí* o *No* para continuar con la evaluación."
            await send_chat2desk_message_direct(client_id, channel_id, clarification_message, transport)
            return True
    
    # ESTADO 2: Esperando calificación (1-5)
    elif evaluation_state == EVALUATION_STATES["WAITING_RATING"]:
        logger.critical(f"🎯 [EVAL] Esperando calificación, recibido: '{text}'")
        
        rating = text.replace(" ", "")
        
        if rating in ["1", "2", "3", "4", "5"]:
            # Calificación válida
            folio = getattr(session, 'evaluation_folio', '')
            
            # 🆕 MARCAR COMO EVALUADO
            current_time = datetime.now().timestamp()
            evaluated_reports[folio] = current_time
            logger.critical(f"📝 [EVALUATED] Reporte {folio} marcado como evaluado")
            
            session.evaluation_state = None
            session.evaluation_folio = None
            session.last_hsm_time = None  # 🆕 LIMPIAR HSM TIME
            session.update_activity()
            
            logger.critical(f"⭐ [EVAL] Calificación recibida: {rating}/5 para folio {folio}")
            
            # Enviar evaluación al CIAC (CONCLUIDO = 1)
            await send_auto_evaluation(
                id_reporte=folio,
                concluido=1,  # Sí está de acuerdo
                calificacion=int(rating),
                comentario=""
            )
            
            thanks_message = "Gracias por tu retroalimentación, tomamos en consideración tus comentarios para mejorar la atención a tus reportes"
            await send_chat2desk_message_direct(client_id, channel_id, thanks_message, transport)
            
            logger.critical(f"⭐ [EVALUACIÓN COMPLETA] Reporte {folio}: Calificación {rating}/5")
            return True
            
        else:
            # Calificación inválida
            logger.critical(f"❌ [EVAL] Calificación inválida: '{text}'")
            invalid_rating_message = "Por favor responde del *1* al *5* para continuar con la evaluación."
            await send_chat2desk_message_direct(client_id, channel_id, invalid_rating_message, transport)
            return True
    
    # ESTADO 3: Esperando motivo de desacuerdo
    elif evaluation_state == EVALUATION_STATES["WAITING_REASON"]:
        logger.critical(f"🎯 [EVAL] Motivo recibido: '{text[:50]}...'")
        
        comentario = text.strip()
        if not comentario:
            clarification_message = "Por favor indícanos brevemente el motivo por el cuál no tuvo resolución."
            await send_chat2desk_message_direct(client_id, channel_id, clarification_message, transport)
            return True

        folio = getattr(session, 'evaluation_folio', '')
        # 🆕 MARCAR COMO EVALUADO
        current_time = datetime.now().timestamp()
        evaluated_reports[folio] = current_time
        logger.critical(f"📝 [EVALUATED] Reporte {folio} marcado como evaluado")
        
        # Finalizar evaluación
        session.evaluation_state = None
        session.evaluation_folio = None
        session.last_hsm_time = None  # 🆕 LIMPIAR HSM TIME
        session.update_activity()
        
        # Enviar evaluación al CIAC (CONCLUIDO = 2)
        await send_auto_evaluation(
            id_reporte=folio,
            concluido=2,  # No está de acuerdo
            calificacion=0,
            comentario=comentario
        )

        await send_reactivation_email_notifications(
            reporte_id=folio,
            comentario=comentario
        )
        
        thanks_message = "Gracias por tu retroalimentación, tomamos en consideración tus comentarios para mejorar la atención a tus reportes"
        await send_chat2desk_message_direct(client_id, channel_id, thanks_message, transport)

        logger.critical(f"❌ [EVALUACIÓN COMPLETA] Reporte {folio}: Desacuerdo - '{comentario[:50]}...'")
        return True
    
    # Estado desconocido
    logger.critical(f"❌ [EVAL] Estado desconocido: '{evaluation_state}'")
    return False


def get_effective_user_message_text(body, reply_context):
    """
    Usa solo la respuesta del usuario cuando el mensaje llega como quoted reply.
    """
    if reply_context and reply_context.get("is_quoted") and reply_context.get("user_response"):
        return reply_context["user_response"].strip()
    return (body or "").strip()


async def send_conclusion_comment_and_image(client_id, channel_id, reporte_id, transport="wa_direct"):
    """
    VERSIÓN MEJORADA: Obtiene y envía el comentario de conclusión e imagen del técnico.
    Supports both wa_direct (WhatsApp) and widget (web chat).
    """
    try:
        logger.critical(f"📄 [CONCLUSION] ===== INICIANDO send_conclusion_comment_and_image =====")
        logger.critical(f"📄 [CONCLUSION] client_id: {client_id}")
        logger.critical(f"📄 [CONCLUSION] channel_id: {channel_id}")
        logger.critical(f"📄 [CONCLUSION] reporte_id: {reporte_id}")

        # Limpiar reporte_id
        clean_reporte_id = str(reporte_id).strip().replace('\r', '').replace('\n', '')
        api_url = f"https://ciac.sanpedro.gob.mx/apisag/api/Operativo/GetFoto?reporteId={clean_reporte_id}"
        
        logger.critical(f"📄 [API CALL] Llamando a: {api_url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client_http:
            response = await client_http.get(api_url)
            logger.critical(f"📄 [API] Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            logger.critical(f"📄 [API] Data recibida: {data}")
        
        if not data or not isinstance(data, list) or len(data) == 0:
            logger.warning(f"📄 [NO DATA] No hay información para reporte {clean_reporte_id}")
            fallback_message = f"📋 *Reporte #{clean_reporte_id} - CONCLUIDO*\n\nTu reporte ha sido atendido satisfactoriamente."
            await send_chat2desk_message_direct(client_id, channel_id, fallback_message, transport)
            return
            
        comentario_data = data[0]
        comentario = comentario_data.get("comentario", "Sin comentario")
        dir_calle = comentario_data.get("dirCalle", "Dirección no disponible")
        dir_colonia = comentario_data.get("dirColonia", "Colonia no disponible") 
        imagen_url = comentario_data.get("imagen", "")

        logger.critical(f"📄 [DATOS] ===== DATOS EXTRAÍDOS =====")
        logger.critical(f"📄 [DATOS] comentario: {comentario}")
        logger.critical(f"📄 [DATOS] dir_calle: {dir_calle}")
        logger.critical(f"📄 [DATOS] dir_colonia: {dir_colonia}")
        logger.critical(f"📄 [DATOS] imagen_url: '{imagen_url}' (tipo: {type(imagen_url)})")
        
        # Enviar comentario de conclusión
        conclusion_message = f"📋 *Reporte #{clean_reporte_id} - CONCLUIDO*\n\n"
        conclusion_message += f"💬 *Comentario de conclusión:*\n_{comentario}_\n\n"
        conclusion_message += f"📍 *Ubicación atendida:*\n{dir_calle}, {dir_colonia}"
        
        logger.critical(f"📄 [MENSAJE] Enviando conclusión...")
        await send_chat2desk_message_direct(client_id, channel_id, conclusion_message, transport)
        logger.critical(f"📄 [MENSAJE] ✅ Mensaje de conclusión enviado")
        
        # ✅ ENVIAR IMAGEN CON LOGS DETALLADOS
        logger.critical(f"📷 [IMAGE CHECK] ===== EVALUANDO IMAGEN =====")
        logger.critical(f"📷 [IMAGE CHECK] imagen_url: '{imagen_url}'")
        logger.critical(f"📷 [IMAGE CHECK] str(imagen_url): '{str(imagen_url)}'")
        logger.critical(f"📷 [IMAGE CHECK] .strip(): '{str(imagen_url).strip()}'")
        logger.critical(f"📷 [IMAGE CHECK] != '0': {str(imagen_url).strip() != '0'}")
        logger.critical(f"📷 [IMAGE CHECK] bool: {bool(str(imagen_url).strip())}")
        
        if imagen_url and str(imagen_url).strip() and str(imagen_url).strip() != "0":
            try:
                clean_image_url = str(imagen_url).strip()
                logger.critical(f"📷 [SENDING] ===== ENVIANDO IMAGEN =====")
                logger.critical(f"📷 [SENDING] URL limpia: {clean_image_url}")

                image_sent = await send_chat2desk_image_direct(client_id, channel_id, clean_image_url, transport)
                
                if image_sent:
                    logger.critical(f"📷 [SUCCESS] ✅ Imagen enviada exitosamente")
                else:
                    logger.error(f"📷 [FAILED] ❌ No se pudo enviar la imagen")
                
            except Exception as img_error:
                logger.error(f"📷 [ERROR] ❌ Error enviando imagen: {str(img_error)}")
                logger.error(f"📷 [ERROR] Traceback: {traceback.format_exc()}")
        else:
            logger.critical(f"📷 [SKIP] ❌ No hay imagen válida para enviar")
            logger.critical(f"📷 [SKIP] Razón: imagen_url='{imagen_url}', strip='{str(imagen_url).strip() if imagen_url else 'None'}'")
        
        logger.critical(f"📄 [CONCLUSION] ===== PROCESO COMPLETADO =====")
        
    except Exception as e:
        logger.error(f"📄 [ERROR] Error en send_conclusion_comment_and_image: {str(e)}")
        logger.error(f"📄 [ERROR] Traceback: {traceback.format_exc()}")
        try:
            fallback_message = f"📋 *Reporte #{reporte_id} - CONCLUIDO*\n\nTu reporte ha sido atendido satisfactoriamente."
            await send_chat2desk_message_direct(client_id, channel_id, fallback_message, transport)
        except Exception as fallback_error:
            logger.error(f"📄 [FALLBACK ERROR] {str(fallback_error)}")

async def send_chat2desk_message_direct(client_id, channel_id, text, transport="wa_direct"):
    """
    Envía mensaje directamente via Chat2Desk API.
    Supports both wa_direct (WhatsApp) and widget (web chat).
    """
    normalized_text = re.sub(r"\s+", " ", (text or "").strip())
    dedup_key = None
    if normalized_text:
        dedup_key = f"{client_id}:{channel_id}:{transport}:{normalized_text}"
        if recent_direct_message_keys.contains(dedup_key):
            logger.warning(f"🚫 [DIRECT DEDUP] Mensaje directo duplicado bloqueado: {normalized_text[:80]}...")
            return False
        recent_direct_message_keys.add(dedup_key)

    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.chat2desk.com.mx/v1/messages",
                headers={
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                },
                json={
                    "client_id": client_id,
                    "channel_id": channel_id,
                    "transport": transport,
                    "text": text
                }
            )
            
        if response.status_code == 200:
            logger.debug(f"✅ Mensaje directo enviado: {normalized_text[:50]}...")
            return True
        else:
            logger.error(f"❌ Error enviando mensaje directo: {response.status_code}")
            if dedup_key:
                recent_direct_message_keys.remove(dedup_key)
            return False
            
    except Exception as e:
        logger.error(f"Error enviando mensaje directo: {str(e)}")
        if dedup_key:
            recent_direct_message_keys.remove(dedup_key)
        return False

async def send_chat2desk_image_direct(client_id, channel_id, image_url, transport="wa_direct"):
    """
    VERSIÓN CORREGIDA según documentación Chat2Desk
    Supports both wa_direct (WhatsApp) and widget (web chat).
    """
    try:
        logger.critical(f"📷 [CORRECTED] ===== USANDO FORMATO CORRECTO =====")

        api_token = os.getenv("CHAT2DESK_API_TOKEN")

        # ✅ FORMATO CORRECTO según documentación
        payload = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": "",
            "attachment": image_url.strip(),
            "attachment_filename": "evidencia.jpg"  # ✅ ESTO FALTABA
        }
        
        logger.critical(f"📷 [CORRECTED] Payload: {payload}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.chat2desk.com.mx/v1/messages",  # Mantenemos este endpoint
                headers={
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
        logger.critical(f"📷 [CORRECTED] Response: {response.status_code}")
        logger.critical(f"📷 [CORRECTED] Text: {response.text}")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success":
                logger.critical(f"📷 [SUCCESS] ✅ Imagen enviada con attachment_filename")
                return True
        
        # Si aún falla, intentar método base64 con filename
        logger.critical(f"📷 [FALLBACK] Intentando base64 con filename...")
        return await send_image_base64_with_filename(client_id, channel_id, image_url, transport)
        
    except Exception as e:
        logger.error(f"📷 [ERROR] {str(e)}")
        return False


async def send_image_base64_with_filename(client_id, channel_id, image_url, transport="wa_direct"):
    """
    Método base64 con attachment_filename
    Supports both wa_direct (WhatsApp) and widget (web chat).
    """
    try:
        # Descargar imagen
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(image_url, headers=headers)
            response.raise_for_status()
            image_data = response.content
            
        logger.critical(f"📷 [BASE64] Descargada: {len(image_data)} bytes")
        
        # Convertir a base64
        import base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{image_b64}"
        
        # ✅ ENVIAR CON FILENAME
        api_token = os.getenv("CHAT2DESK_API_TOKEN")

        payload = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": "",
            "attachment": data_url,
            "attachment_filename": "evidencia.jpg"  # ✅ FILENAME REQUERIDO
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.chat2desk.com.mx/v1/messages",
                headers={
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
        logger.critical(f"📷 [BASE64] Response: {response.status_code}")
        logger.critical(f"📷 [BASE64] Text: {response.text}")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success":
                logger.critical(f"📷 [SUCCESS] ✅ Base64 enviado con filename")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"📷 [BASE64 ERROR] {str(e)}")
        return False


async def download_and_upload_image(client_id, channel_id, image_url, transport="wa_direct"):
    """
    Descarga imagen y la sube como base64 - VERSIÓN MEJORADA
    Supports both wa_direct (WhatsApp) and widget (web chat).
    """
    try:
        logger.critical(f"📷 [DOWNLOAD] ===== DESCARGANDO IMAGEN =====")
        
        # ✅ DESCARGAR CON HEADERS DE NAVEGADOR
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(image_url, headers=headers)
            response.raise_for_status()
            image_data = response.content
            content_type = response.headers.get('content-type', 'image/jpeg')
            
        logger.critical(f"📷 [DOWNLOAD] ✅ Descargada: {len(image_data)} bytes")
        logger.critical(f"📷 [DOWNLOAD] Content-Type: {content_type}")
        
        # Verificar que SÍ es una imagen por los primeros bytes
        if image_data.startswith(b'\xff\xd8\xff'):  # JPEG
            mime_type = 'image/jpeg'
            logger.critical(f"📷 [DOWNLOAD] ✅ Confirmado: es JPEG")
        elif image_data.startswith(b'\x89PNG'):  # PNG
            mime_type = 'image/png'
            logger.critical(f"📷 [DOWNLOAD] ✅ Confirmado: es PNG")
        else:
            # Asumir JPEG si no podemos detectar
            mime_type = 'image/jpeg'
            logger.warning(f"📷 [DOWNLOAD] ⚠️ Tipo no detectado, asumiendo JPEG")
        
        # Limitar tamaño
        if len(image_data) > 5 * 1024 * 1024:  # 5MB
            logger.error(f"📷 [SIZE] ❌ Muy grande: {len(image_data)} bytes")
            return False
        
        # Convertir a base64
        import base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        data_url = f"data:{mime_type};base64,{image_b64}"
        
        logger.critical(f"📷 [BASE64] ✅ Convertida: {len(data_url)} chars")
        
        # Enviar
        api_token = os.getenv("CHAT2DESK_API_TOKEN")

        payload = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": "",
            "attachment": data_url
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.chat2desk.com.mx/v1/messages",
                headers={
                    "Authorization": api_token,
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
        logger.critical(f"📷 [UPLOAD] Response: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success":
                logger.critical(f"📷 [SUCCESS] ✅ Imagen subida como base64")
                return True
        
        logger.error(f"📷 [UPLOAD] ❌ Error: {response.text}")
        return False
        
    except Exception as e:
        logger.error(f"📷 [DOWNLOAD ERROR] {str(e)}")
        return False

async def send_auto_evaluation(id_reporte: str, concluido: int, calificacion: int, comentario: str = ""):
    """
    Envía la evaluación automática al endpoint del CIAC.
    
    Args:
        id_reporte: ID del reporte
        concluido: 1 = Sí está de acuerdo, 2 = No está de acuerdo
        calificacion: 1-5 (solo si concluido=1)
        comentario: Motivo de desacuerdo (solo si concluido=2)
    """
    try:
        payload = {
            "idReporte": int(id_reporte),
            "idValoracionConcluido": concluido,
            "idValoracionCalificacion": calificacion,
            "valoracionComentarios": comentario or "Sin comentario"
        }
        
        logger.critical(f"📤 [AUTO-EVALUACIÓN] Enviando: {payload}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://ciac.sanpedro.gob.mx/apisag/api/AutoEvaluacion/a73a78a5-3a3f-479e-ae11-063c9014f5b7",
                headers={
                    "accept": "*/*",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
        if response.status_code == 200:
            logger.critical(f"✅ [AUTO-EVALUACIÓN] Enviada exitosamente para reporte {id_reporte}")
        else:
            logger.error(f"❌ [AUTO-EVALUACIÓN] Error {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"Error enviando auto-evaluación: {str(e)}")


REACTIVATION_NOTIFICATION_RECIPIENTS = [
    "aalvarado@sanpedro.gob.mx",
    "andres.alvarado@sanpedro.gob.mx",
    "daniel.galvan@sanpedro.gob.mx",
]


def build_reactivation_email_html(reporte_id: str, comentario: str) -> str:
    reporte_label = html.escape(str(reporte_id or "Sin folio"))
    comentario_html = html.escape(comentario or "Sin comentario").replace("\n", "<br>")
    fecha_html = html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1f2937;">
        <h2>Solicitud de reactivación de reporte</h2>
        <p>Un ciudadano indicó que <strong>no está de acuerdo con la resolución</strong> de su reporte.</p>
        <p><strong>Reporte:</strong> {reporte_label}</p>
        <p><strong>Fecha:</strong> {fecha_html}</p>
        <p><strong>Motivo capturado:</strong></p>
        <div style="padding: 12px; background: #f3f4f6; border-left: 4px solid #dc2626;">
          {comentario_html}
        </div>
      </body>
    </html>
    """.strip()


async def send_reactivation_email_notifications(reporte_id: str, comentario: str):
    """
    Solicita al CIAC el envío de correos cuando el ciudadano no acepta la resolución.
    """
    report_id_value = 0
    try:
        report_id_value = int(str(reporte_id).strip())
    except (TypeError, ValueError):
        logger.warning(f"⚠️ [MAIL] reporte_id inválido para correo: {reporte_id}")

    titulo = "REPORTE NO CONCLUIDO"
    code_html = build_reactivation_email_html(reporte_id, comentario)
    endpoint = "https://ciac.sanpedro.gob.mx/apisag/api/LogNotificacionesMail/a73a78a5-3a3f-479e-ae11-063c9014f5b7"

    logger.critical(
        f"📧 [MAIL] Iniciando notificaciones de reactivación para reporte {reporte_id} "
        f"a {len(REACTIVATION_NOTIFICATION_RECIPIENTS)} destinatarios"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        for correo in REACTIVATION_NOTIFICATION_RECIPIENTS:
            payload = {
                "titulo": titulo,
                "correo": correo,
                "codeHTML": code_html,
                "reporteId": report_id_value,
            }

            try:
                logger.critical(
                    f"📧 [MAIL] Enviando notificación a {correo} "
                    f"para reporte {reporte_id} vía LogNotificacionesMail"
                )
                response = await client.post(
                    endpoint,
                    headers={
                        "accept": "*/*",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code == 200:
                    logger.critical(
                        f"✅ [MAIL] Notificación de reactivación enviada a {correo} "
                        f"para reporte {reporte_id}. Respuesta: {response.text[:300]}"
                    )
                else:
                    logger.error(f"❌ [MAIL] Error {response.status_code} enviando notificación a {correo}: {response.text}")
            except Exception as e:
                logger.error(f"❌ [MAIL] Error enviando notificación de reactivación a {correo}: {str(e)}")

# ===============================================
# FIN DEL SISTEMA DE EVALUACIÓN
# ===============================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = os.environ.get("VOICE_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")

OPENAI_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
OPENAI_MAX_RETRIES = 3

# ========= EQUIPO CIAC ============================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=OPENAI_HTTP_TIMEOUT,
    max_retries=OPENAI_MAX_RETRIES,
)


SPECIAL_NUMBER = "5218114660135"
# ========= EQUIPO CIAC ============================

# Diccionario para almacenar reportes en progreso
report_sessions = {}  # key: phone_number, value: {images: [], image_descriptions: [], location: str, timestamp: datetime}
reports_lock = threading.Lock()
report_sessions_lock = RLock()  # More robust than a simple Lock
reports_in_progress = {}
transferred_numbers = {}  # key: phone_number, value: expiration_timestamp
transfer_guard_context = {}  # key: message_id, value: contextual metadata for guarded transfers
transfer_timeout = 15 * 60  # 15 minutes in seconds
last_response_time = {}  # Para rastrear cuándo se envió la última respuesta a cada número
completed_reports = {}  # key: phone_number, value: {timestamp: datetime, folio: str}
finalized_report_numbers = set()
# Ahora, añade esta nueva función para verificar si un número ya tiene un reporte reciente
recently_returned_to_bot = {}
bot_returned_at = {}
STALE_RETURN_EVENT_TOLERANCE_SECONDS = 1.0
STALE_INBOUND_EVENT_MAX_AGE_SECONDS = 30 * 60
BOT_GRACE_PERIOD = 10
user_answers = {}
closed_by_inactivity = {}  # key: phone_number, value: expiration_timestamp
INACTIVITY_COOLDOWN = 15 * 60  # 15 minutos en segundos - periodo para NO reactivar después de cierre
hsm_sent_reports = {}
sent_evaluation_messages = {} 

# ===============================================================
# OPTIMIZACIÓN: Crear índices una sola vez al iniciar el servidor
# ===============================================================

class StreetsAndColoniesOptimizer:
    """
    🚀 OPTIMIZACIÓN EXPANDIDA: Calles + Colonias reales de San Pedro
    """
    def __init__(self):
        print(f"🚀 [OPTIMIZER INIT] Iniciando con {len(SAN_PEDRO_STREETS_REAL)} calles y {len(SAN_PEDRO_COLONIES)} colonias")
        
        self.original_streets = SAN_PEDRO_STREETS_REAL
        self.original_colonies = SAN_PEDRO_COLONIES
        
        # Índices para calles
        self.normalized_streets = {}
        self.street_word_index = {}
        
        # Índices para colonias  
        self.normalized_colonies = {}
        self.colony_word_index = {}
        
        self._build_indexes()
        
        # NUEVO: Verificar que los índices se construyeron
        print(f"🚀 [OPTIMIZER INIT] Índices construidos:")
        print(f"   - normalized_streets: {len(self.normalized_streets)} entradas")
        print(f"   - normalized_colonies: {len(self.normalized_colonies)} entradas")
        print(f"   - ¿'centro' normalizado existe? {'centro' in self.normalized_colonies}")
        
        # Test inmediato
        test_result = self.find_closest_colony("centro")
        print(f"🚀 [OPTIMIZER TEST] Búsqueda de 'centro': {test_result}")
    
    def _normalize_text(self, text):
        """Normaliza texto para comparación (sin acentos, minúsculas)"""
        return (text.lower()
                .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                .replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
                .strip())
    
    def _build_indexes(self):
        """🚀 Construye índices optimizados para CALLES Y COLONIAS"""
        print(f"🚀 [OPTIMIZER] Construyendo índices para {len(self.original_streets)} calles y {len(self.original_colonies)} colonias...")
        
        # Índices para calles
        for street in self.original_streets:
            normalized = self._normalize_text(street)
            self.normalized_streets[normalized] = street
            
            words = normalized.split()
            for word in words:
                if word not in self.street_word_index:
                    self.street_word_index[word] = []
                self.street_word_index[word].append(street)
        
        # Índices para colonias
        for colony in self.original_colonies:
            normalized = self._normalize_text(colony)
            self.normalized_colonies[normalized] = colony
            
            words = normalized.split()
            for word in words:
                if word not in self.colony_word_index:
                    self.colony_word_index[word] = []
                self.colony_word_index[word].append(colony)
        
        print(f"✅ [OPTIMIZER] Índices listos: {len(self.normalized_streets)} calles, {len(self.normalized_colonies)} colonias")
    
    def find_closest_street(self, input_text):
        """🚀 Encuentra la calle más parecida"""
        return self._find_closest_item(input_text, self.normalized_streets, self.street_word_index)
    
    def find_closest_colony(self, input_text):
        """🚀 NUEVO: Encuentra la colonia más parecida"""
        return self._find_closest_item(input_text, self.normalized_colonies, self.colony_word_index)
    
    def _find_closest_item(self, input_text, normalized_dict, word_index):
        """🚀 Lógica genérica para buscar calles o colonias"""
        if not input_text or len(input_text.strip()) < 2:
            return None, 0
        
        input_clean = self._normalize_text(input_text)
        
        # 1. ⚡ Búsqueda exacta
        if input_clean in normalized_dict:
            return normalized_dict[input_clean], 1.0
        
        # 2. ⚡ Búsqueda por palabras clave
        input_words = input_clean.split()
        candidates = set()
        
        for word in input_words:
            if word in word_index:
                candidates.update(word_index[word])
        
        if candidates:
            best_match = None
            best_score = 0
            
            for candidate in candidates:
                candidate_normalized = self._normalize_text(candidate)
                similarity = difflib.SequenceMatcher(None, input_clean, candidate_normalized).ratio()
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = candidate
            
            if best_match and best_score >= 0.6:
                return best_match, best_score
        
        # 3. ⚡ Fuzzy matching completo
        normalized_list = list(normalized_dict.keys())
        close_matches = difflib.get_close_matches(input_clean, normalized_list, n=1, cutoff=0.6)
        
        if close_matches:
            matched_normalized = close_matches[0]
            original_item = normalized_dict[matched_normalized]
            similarity = difflib.SequenceMatcher(None, input_clean, matched_normalized).ratio()
            return original_item, similarity
        
        return None, 0
    
def validate_street_exists(street_name):
    """🚀 Validación de calles"""
    if not street_name:
        return False, "No se proporcionó nombre de calle"
    
    closest_street, similarity = find_closest_street(street_name)
    
    if closest_street and similarity >= 0.9:
        return True, f"Calle válida: {closest_street}"
    elif closest_street and similarity >= 0.7:
        return True, f"Calle similar: {closest_street} (verifica ortografía)"
    else:
        return False, f"Calle '{street_name}' no encontrada en San Pedro"
        
    
def validate_colony_exists(colony_name):
    """🚀 NUEVO: Validación de colonias"""
    if not colony_name:
        return False, "No se proporcionó nombre de colonia"
    
    closest_colony, similarity = find_closest_colony(colony_name)
    
    if closest_colony and similarity >= 0.9:
        return True, f"Colonia válida: {closest_colony}"
    elif closest_colony and similarity >= 0.7:
        return True, f"Colonia similar: {closest_colony} (verifica ortografía)"
    else:
        return False, f"Colonia '{colony_name}' no encontrada en San Pedro"

# ===============================================================
# CREAR INSTANCIA GLOBAL (una sola vez al iniciar)
# ===============================================================
streets_and_colonies_optimizer = StreetsAndColoniesOptimizer()

# ===============================================================
# FUNCIONES WRAPPER PARA USO FÁCIL
# ===============================================================

def find_closest_street(input_text):
    """🚀 Wrapper optimizado - Tiempo: <1ms"""
    return streets_and_colonies_optimizer.find_closest_street(input_text)


def find_closest_colony(input_text):
    """🚀 Wrapper optimizado para colonias - Tiempo: <1ms"""
    return streets_and_colonies_optimizer.find_closest_colony(input_text)

def detect_and_store_user_data_with_real_streets_and_colonies(from_number: str, body: str):
    """
    🚀 VERSIÓN CORREGIDA Y OPTIMIZADA: Usa arrays importados y patrones flexibles
    """
    logger.critical(f"🔍 [REAL STREETS] Analizando: {from_number} - '{body[:50]}...'")
    
    body_lower = body.lower()
    saved_fields = []
    
    # ===============================================================
    # 1. DETECCIÓN DE CALLES CON OPTIMIZACIÓN MEJORADA
    # ===============================================================
    
    street_patterns_real = [
        # Patrones específicos (mantener los existentes)
        r"(?i)(?:está|esta|ubicad[oa]?)\s+en\s+([a-záéíóúñ\s\d]+?)(?:\s+(?:cruz|esquina|y)\s+con\s+([a-záéíóúñ\s]+?))?(?:\s|,|$)",
        r"(?i)en\s+(?:la\s+)?calle\s+([a-záéíóúñ\s\d]+?)(?:\s+(?:cruz|esquina|y|número|#|\d)|,|$)",
        r"(?i)sobre\s+([a-záéíóúñ\s\d]+?)(?:\s+(?:cruz|esquina|y|número|#|\d)|,|$)",
        r"(?i)(?:en|de)\s+([a-záéíóúñ\s\d]{4,}?)(?:\s+(?:cruz|esquina|y|número|#|\d)|,|$)",
        
        # 🚀 NUEVOS PATRONES MÁS FLEXIBLES
        # Capturar nombres propios que podrían ser calles (2-3 palabras capitalizadas)
        r"(?i)\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})\b",
        
        # Capturar después de "en" sin requerir "calle" (más flexible)
        r"(?i)(?:^|\s)en\s+([a-záéíóúñ\s\d]{3,20})(?:\s+(?:número|#|\d)|,|$)",
        
        # Capturar nombres al inicio del mensaje
        r"(?i)^([a-záéíóúñ\s\d]{3,25})(?:\s+(?:número|#|\d)|,)",
        
        # Capturar entre comas (formato común: "calle, número, colonia")
        r"(?i)(?:^|,\s*)([a-záéíóúñ\s\d]{3,25})(?=\s*,|\s*\d|\s*$)",
    ]
    
    # Lista de palabras que NO son calles (filtros mejorados)
    excluded_street_words = [
        "problema", "reporte", "tengo", "hay", "está", "esta", "es", "son",
        "muy", "poco", "mucho", "todo", "nada", "algo", "aquí", "ahí", "allí",
        "buenos", "días", "tardes", "noches", "hola", "gracias", "por", "favor",
        "quiero", "necesito", "puedo", "debo", "voy", "vamos", "hacer", "decir",
        "colonia", "col", "número", "casa", "edificio", "piso", "departamento"
    ]
    
    for pattern in street_patterns_real:
        match = re.search(pattern, body)
        if match:
            street_candidate = match.group(1).strip()
            
            # Filtrar palabras excluidas
            if (len(street_candidate) >= 3 and 
                not any(excluded in street_candidate.lower() for excluded in excluded_street_words)):
                
                # 🚀 Búsqueda optimizada con threshold más permisivo
                closest_street, similarity = find_closest_street(street_candidate)
                
                if closest_street and similarity >= 0.6:  # Reducido de 0.7 a 0.6
                    save_user_answer(from_number, "selection5", closest_street)
                    saved_fields.append(("selection5", f"{closest_street} (sim: {similarity:.2f})"))
                    logger.critical(f"💾 [REAL STREET] '{street_candidate}' → '{closest_street}' (sim: {similarity:.2f})")
                    
                    # Si hay "cruz con" detectar la segunda calle
                    if len(match.groups()) > 1 and match.group(2):
                        cross_street = match.group(2).strip()
                        closest_cross, cross_similarity = find_closest_street(cross_street)
                        
                        if closest_cross and cross_similarity >= 0.5:  # Threshold más bajo para cruce
                            enhanced_street = f"{closest_street} cruz con {closest_cross}"
                            save_user_answer(from_number, "selection5", enhanced_street)
                            saved_fields[-1] = ("selection5", enhanced_street)
                            logger.critical(f"💾 [CROSS STREET] + '{closest_cross}' → '{enhanced_street}'")
                    break
                else:
                    # 🆕 Si no encuentra coincidencia exacta, guardar como candidato si parece válido
                    if (len(street_candidate) >= 4 and 
                        street_candidate.replace(" ", "").replace("-", "").isalpha() and
                        any(char.isupper() for char in street_candidate)):  # Tiene mayúsculas (nombre propio)
                        
                        save_user_answer(from_number, "selection5", street_candidate.title())
                        saved_fields.append(("selection5", f"{street_candidate.title()} (candidato)"))
                        logger.critical(f"💾 [STREET CANDIDATE] '{street_candidate}' guardado como candidato")
                        break
                    else:
                        logger.warning(f"⚠️ [STREET NOT FOUND] '{street_candidate}' no encontrada (sim: {similarity:.2f})")
    
    # ===============================================================
    # 2. DETECCIÓN DE COLONIAS - USANDO ARRAY IMPORTADO Y find_closest_colony
    # ===============================================================
    
    colony_patterns_real = [
        # Patrones específicos existentes
        r"(?i)colonia\s+([a-záéíóúñ\s]+?)(?:\s|,|$)",
        r"(?i),\s*(?:colonia|col\.?)\s+([a-záéíóúñ\s]+?)(?:\s|$)",
        
        # 🚀 USAR EL ARRAY IMPORTADO SAN_PEDRO_COLONIES dinámicamente
        r"(?i)\b(" + "|".join([col.lower() for col in SAN_PEDRO_COLONIES]) + r")\b",
        
        # 🚀 NUEVOS PATRONES MÁS FLEXIBLES
        # Capturar después de coma (segundo elemento común en direcciones)
        r"(?i).*,\s*([a-záéíóúñ\s]{4,25})$",
        
        # Capturar nombres propios que podrían ser colonias
        r"(?i)\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)\b(?=\s*$)",
        
        # Capturar palabras que terminan en patrones típicos de colonias
        r"(?i)\b([a-záéíóúñ\s]*(?:centro|valle|lomas|bosques|jardines|residencial|colonial|heights|park|fraccionamiento))\b",
    ]
    
    # Lista de palabras que NO son colonias
    excluded_colony_words = [
        "problema", "reporte", "calle", "avenida", "número", "casa", "edificio",
        "piso", "departamento", "oficina", "local", "negocio", "tienda", "tengo",
        "hay", "está", "esta", "buenos", "días", "hola", "gracias"
    ]
    
    for pattern in colony_patterns_real:
        match = re.search(pattern, body)
        if match:
            colony_candidate = match.group(1).strip() if match.group(1) else match.group(0).strip()
            
            # Filtrar palabras excluidas
            if (len(colony_candidate) >= 3 and 
                not any(excluded in colony_candidate.lower() for excluded in excluded_colony_words)):
                
                # 🚀 USAR find_closest_colony con threshold permisivo
                closest_colony, similarity = find_closest_colony(colony_candidate)
                
                if closest_colony and similarity >= 0.6:  # Threshold permisivo
                    save_user_answer(from_number, "selection7", closest_colony)
                    saved_fields.append(("selection7", f"{closest_colony} (sim: {similarity:.2f})"))
                    logger.critical(f"💾 [REAL COLONY] '{colony_candidate}' → '{closest_colony}' (sim: {similarity:.2f})")
                    break
                else:
                    # 🆕 Verificar si es una colonia conocida directamente del array
                    is_known_colony = any(known.lower() in colony_candidate.lower() for known in SAN_PEDRO_COLONIES)
                    
                    if is_known_colony or (len(colony_candidate) >= 4 and 
                                         colony_candidate.replace(" ", "").isalpha()):
                        save_user_answer(from_number, "selection7", colony_candidate.title())
                        saved_fields.append(("selection7", f"{colony_candidate.title()} (candidato)"))
                        logger.critical(f"💾 [COLONY CANDIDATE] '{colony_candidate.title()}' guardado como candidato")
                        break
                    else:
                        logger.warning(f"⚠️ [COLONY NOT FOUND] '{colony_candidate}' no encontrada (sim: {similarity:.2f})")
    
    # ===============================================================
    # 3. DETECCIÓN DIRECTA POR PALABRAS CLAVE (NUEVO)
    # ===============================================================
    
    # 🚀 Búsqueda directa sin patrones regex para casos simples
    body_words = body_lower.split()
    
    # Buscar calles directamente en las palabras
    if not any("selection5" in field[0] for field in saved_fields):  # Solo si no se encontró calle
        for word in body_words:
            if len(word) >= 4:  # Palabras de al menos 4 caracteres
                closest_street, similarity = find_closest_street(word)
                if closest_street and similarity >= 0.8:  # Threshold alto para búsqueda directa
                    save_user_answer(from_number, "selection5", closest_street)
                    saved_fields.append(("selection5", f"{closest_street} (directo: {similarity:.2f})"))
                    logger.critical(f"💾 [DIRECT STREET] '{word}' → '{closest_street}' (sim: {similarity:.2f})")
                    break
    
    # Buscar colonias directamente en las palabras
    if not any("selection7" in field[0] for field in saved_fields):  # Solo si no se encontró colonia
        for word in body_words:
            if len(word) >= 4:  # Palabras de al menos 4 caracteres
                closest_colony, similarity = find_closest_colony(word)
                if closest_colony and similarity >= 0.8:  # Threshold alto para búsqueda directa
                    save_user_answer(from_number, "selection7", closest_colony)
                    saved_fields.append(("selection7", f"{closest_colony} (directo: {similarity:.2f})"))
                    logger.critical(f"💾 [DIRECT COLONY] '{word}' → '{closest_colony}' (sim: {similarity:.2f})")
                    break
    
    # ===============================================================
    # 4. OTROS CAMPOS (LÓGICA MEJORADA)
    # ===============================================================
    
    patterns = {
        # Patrones existentes
        "selection2": r"(?i)(?:nombre\s*[:=]\s*|me\s+llamo\s+|soy\s+)([a-záéíóúñ\s]+?)(?:\s|,|$)",
        "selection4": r"(?i)(?:tipo\s*[:=]\s*|problema\s*[:=]?\s*|reporte\s*[:=]?\s*)([^\n,]+)",
        "selection6": r"(?i)(?:n[uú]mero\s*[:=]\s*|#\s*)(\d{1,5})\b",
        
        # 🚀 NUEVOS PATRONES MÁS FLEXIBLES
        "selection2_alt": r"(?i)^([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)",  # Nombre al inicio
        "selection6_alt": r"(?i)\b(\d{1,4})\b(?!\d)",  # Cualquier número de 1-4 dígitos
    }

    for selection_key, pattern in patterns.items():
        # Limpiar el key (remover _alt si existe)
        clean_key = selection_key.replace("_alt", "")
        
        matches = re.findall(pattern, body)
        for match in matches:
            value = match.strip()
            
            # Validaciones específicas
            if clean_key == "selection2" and len(value) >= 2:  # Nombre válido
                save_user_answer(from_number, clean_key, value.title())
                saved_fields.append((clean_key, value.title()))
                break
            elif clean_key == "selection4" and len(value) >= 5:  # Descripción válida
                save_user_answer(from_number, clean_key, value)
                saved_fields.append((clean_key, value))
                break
            elif clean_key == "selection6" and value.isdigit():  # Número válido
                num_val = int(value)
                if 1 <= num_val <= 99999:
                    save_user_answer(from_number, clean_key, value)
                    saved_fields.append((clean_key, value))
                    break
    
    # ===============================================================
    # 5. LOG DE RESULTADOS MEJORADO
    # ===============================================================
    
    if saved_fields:
        log_summary = "; ".join([f"{key}='{val}'" for key, val in saved_fields])
        logger.critical(f"[{from_number}] ✅ CORREGIDO - Campos detectados: {log_summary}")
        
        # 🆕 Log adicional de estadísticas
        logger.critical(f"[{from_number}] 📊 STATS - Total campos: {len(saved_fields)}, " +
                       f"Arrays usados: SAN_PEDRO_COLONIES({len(SAN_PEDRO_COLONIES)} items)")
    else:
        logger.debug(f"[{from_number}] ❌ CORREGIDO - No se detectó información válida en: {body.strip()}")
        
        # 🆕 Log de debug para entender por qué no se detectó nada
        logger.debug(f"[{from_number}] 🔍 DEBUG - Palabras analizadas: {body_lower.split()[:10]}")  

# ===============================================================
# PERFORMANCE STATS (opcional para debug)
# ===============================================================

def detect_and_store_user_data(from_number: str, body: str):
    """
    🚀 Wrapper que usa la versión optimizada con calles reales de San Pedro
    """
    return detect_and_store_user_data_with_real_streets_and_colonies(from_number, body)

def get_streets_performance_stats():
    """🚀 Stats de rendimiento del optimizador"""
    return {
        "total_streets": len(streets_and_colonies_optimizer.original_streets),
        "normalized_streets": len(streets_and_colonies_optimizer.normalized_streets),
        "word_index_size": len(streets_and_colonies_optimizer.word_index),
        "memory_efficient": True,
        "avg_search_time_ms": "<1ms"
    }

def extract_reply_context(payload):
    """
    Extrae el contexto de respuesta (reply) O mensaje citado de WhatsApp.
    Versión mejorada que maneja tanto replies como quoted messages.
    
    Args:
        payload (dict): El payload recibido de Chat2Desk
        
    Returns:
        dict: Información sobre la respuesta, incluyendo el mensaje original
    """
    reply_info = {
        'is_reply': False,
        'original_message': None,
        'reply_to_id': None,
        'is_quoted': False,
        'user_response': None
    }
    
    try:
        text = payload.get('text', '')
        
        # NUEVO: Primero verificar si es un mensaje citado
        quoted_info = extract_quoted_message_content(text)
        if quoted_info['is_quoted']:
            reply_info.update({
                'is_reply': True,  # Tratamos quoted como reply para propósitos de procesamiento
                'is_quoted': True,
                'original_message': quoted_info['quoted_text'],
                'user_response': quoted_info['user_response'],
                'reply_to_id': 'quoted_message'
            })
            logger.debug(f"Quoted message detected: {reply_info}")
            return reply_info
        
        # Continuar con detección de replies normales
        # Opción 1: Campo 'reply_to' directo
        if payload.get('reply_to'):
            reply_info['is_reply'] = True
            reply_info['reply_to_id'] = payload.get('reply_to')
            reply_info['original_message'] = payload.get('reply_to_text', '')
            
        # Opción 2: Campo 'quoted_message' o similar
        elif payload.get('quoted_message'):
            reply_info['is_reply'] = True
            quoted = payload.get('quoted_message', {})
            reply_info['original_message'] = quoted.get('text', '')
            reply_info['reply_to_id'] = quoted.get('id')
            
        # Opción 3: En el campo 'context' que a veces usa Chat2Desk
        elif payload.get('context', {}).get('quoted_message'):
            reply_info['is_reply'] = True
            quoted = payload['context']['quoted_message']
            reply_info['original_message'] = quoted.get('text', '')
            reply_info['reply_to_id'] = quoted.get('id')
            
        # Opción 4: Buscar en metadata adicional
        elif payload.get('metadata', {}).get('reply'):
            reply_info['is_reply'] = True
            reply_data = payload['metadata']['reply']
            reply_info['original_message'] = reply_data.get('text', '')
            reply_info['reply_to_id'] = reply_data.get('id')
            
        logger.debug(f"Reply context extracted: {reply_info}")
        
    except Exception as e:
        logger.error(f"Error extracting reply context: {str(e)}")
        
    return reply_info

def process_reply_message(from_number, body, reply_context):
    """
    Procesa un mensaje que es respuesta a otro mensaje específico.
    
    Args:
        from_number (str): Número del remitente
        body (str): Contenido del mensaje de respuesta
        reply_context (dict): Contexto de la respuesta extraído
        
    Returns:
        str: Mensaje enriquecido con contexto
    """
    try:
        if not reply_context['is_reply']:
            return body
            
        original_message = reply_context.get('original_message', '')
        
        # Crear un mensaje contextualizado
        contextualized_message = f"[Respondiendo a: '{original_message[:50]}...'] {body}"
        
        logger.critical(f"🔗 [REPLY DETECTED] {from_number} respondió '{body}' a '{original_message[:30]}...'")
        
        # Si el mensaje original era una pregunta específica, intentar categorizar la respuesta
        original_lower = original_message.lower()
        
        # Detectar si es respuesta a pregunta sobre número/dirección
        if any(keyword in original_lower for keyword in ['número', 'numero', 'dirección', 'direccion', 'calle']):
            # Si la respuesta es un número, probablemente es un número de casa
            if body.strip().isdigit():
                save_user_answer(from_number, "selection6", body.strip())
                logger.critical(f"💾 [REPLY AUTO-SAVE] Número guardado por respuesta: {body}")
                
        # Detectar si es respuesta a pregunta sobre colonia
        elif any(keyword in original_lower for keyword in ['colonia', 'col.', 'barrio', 'zona']):
            save_user_answer(from_number, "selection7", body.strip())
            logger.critical(f"💾 [REPLY AUTO-SAVE] Colonia guardada por respuesta: {body}")
            
        # Detectar si es respuesta a pregunta sobre tipo de problema
        elif any(keyword in original_lower for keyword in ['tipo', 'problema', 'reporte', 'motivo']):
            save_user_answer(from_number, "selection4", body.strip())
            logger.critical(f"💾 [REPLY AUTO-SAVE] Problema guardado por respuesta: {body}")
            
        return contextualized_message
        
    except Exception as e:
        logger.error(f"Error processing reply message: {str(e)}")
        return body

def update_user_activity_on_reply(from_number):
    """
    Actualiza la actividad del usuario cuando responde, evitando timeouts incorrectos.
    
    Args:
        from_number (str): Número del usuario
    """
    try:
        # Actualizar sesión de usuario si existe
        if from_number in user_sessions:
            user_sessions[from_number].update_activity()
            logger.debug(f"🔄 [ACTIVITY] Actividad actualizada por reply para {from_number}")
            
        # Actualizar sesión de reporte si existe
        if from_number in report_sessions:
            with report_sessions_lock:
                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                logger.debug(f"🔄 [REPORT ACTIVITY] Reporte actualizado por reply para {from_number}")
                
        # Actualizar tiempo de última respuesta
        last_response_time[from_number] = datetime.now().timestamp()
        
    except Exception as e:
        logger.error(f"Error updating activity on reply: {str(e)}")

async def monitor_reply_detection():
    """
    Tarea de background para monitorear la detección de respuestas.
    """
    while True:
        try:
            await asyncio.sleep(300)  # Cada 5 minutos
            
            total_sessions = len(user_sessions)
            report_sessions_count = len(report_sessions)
            
            logger.info(f"📊 [REPLY STATS] Sesiones activas: {total_sessions}, Reportes en progreso: {report_sessions_count}")
            
            # Contar cuántas sesiones tienen actividad reciente
            now = datetime.now(pytz.timezone('America/Mexico_City'))
            recent_activity = 0
            
            for number, session in user_sessions.items():
                if (now - session.last_active).total_seconds() < 300:  # Últimos 5 minutos
                    recent_activity += 1
                    
            logger.info(f"📊 [REPLY STATS] Sesiones con actividad reciente (5 min): {recent_activity}")
            
        except Exception as e:
            logger.error(f"Error in reply detection monitor: {str(e)}")

def extract_quoted_message_content(text):
    """
    Extrae el contenido de un mensaje citado de WhatsApp.
    SOLO detecta el patrón específico: « texto citado » \n respuesta
    
    Args:
        text (str): Texto completo del mensaje
        
    Returns:
        dict: Información del mensaje citado y respuesta del usuario
    """
    import re
    
    result = {
        'is_quoted': False,
        'quoted_text': None,
        'user_response': None,
        'original_text': text
    }
    
    try:
        # ÚNICO PATRÓN: « texto citado » \n respuesta_usuario
        pattern = r'«\s*(.*?)\s*»\s*\n\s*(.*)'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            quoted_text = match.group(1).strip()
            user_response = match.group(2).strip()
            
            
            # Validaciones adicionales para evitar falsos positivos
            if (quoted_text and user_response and 
                len(user_response) > 0 and 
                len(user_response) < len(quoted_text)):  # La respuesta debe ser más corta que lo citado
                
                result.update({
                    'is_quoted': True,
                    'quoted_text': quoted_text,
                    'user_response': user_response
                })
                
                logger.debug(f"✅ QUOTED MATCH: Citado='{quoted_text[:30]}...', Respuesta='{user_response}'")
                return result
            else:
                logger.debug(f"❌ QUOTED REJECTED: Citado='{quoted_text[:30]}...', Respuesta='{user_response}' (no cumple validaciones)")
                        
    except Exception as e:
        logger.error(f"Error extracting quoted content: {str(e)}")
    
    return result

def process_quoted_message(from_number, text, quoted_info):
    """
    Procesa un mensaje que contiene texto citado y extrae la respuesta del usuario.
    
    Args:
        from_number (str): Número del usuario
        text (str): Texto completo del mensaje
        quoted_info (dict): Información del mensaje citado
        
    Returns:
        str: Solo la respuesta del usuario
    """
    try:
        if not quoted_info['is_quoted']:
            return text
            
        user_response = quoted_info['user_response']
        quoted_text = quoted_info['quoted_text']
        
        logger.critical(f"📝 [QUOTED PROCESSING] Usuario {from_number}: '{user_response}' (citó: '{quoted_text[:30]}...')")
        
        # Actualizar actividad del usuario
        update_user_activity_on_reply(from_number)
        
        # Intentar detectar el tipo de respuesta basándose en el texto citado
        if quoted_text:
            quoted_lower = quoted_text.lower()
            
            # Detectar preguntas sobre ubicación/dirección
            if any(keyword in quoted_lower for keyword in ['calle', 'dirección', 'direccion', 'donde', 'dónde', 'ubicación', 'ubicacion']):
                if len(user_response) > 2 and not user_response.isdigit():
                    save_user_answer(from_number, "selection5", user_response)
                    logger.critical(f"💾 [QUOTED SAVE] Calle guardada: {user_response}")
                elif user_response.isdigit():
                    save_user_answer(from_number, "selection6", user_response) 
                    logger.critical(f"💾 [QUOTED SAVE] Número guardado: {user_response}")
                    
            # Detectar preguntas sobre número
            elif any(keyword in quoted_lower for keyword in ['número', 'numero']):
                if user_response.isdigit():
                    save_user_answer(from_number, "selection6", user_response)
                    logger.critical(f"💾 [QUOTED SAVE] Número guardado: {user_response}")
                    
            # Detectar preguntas sobre colonia
            elif any(keyword in quoted_lower for keyword in ['colonia', 'col.', 'barrio']):
                save_user_answer(from_number, "selection7", user_response)
                logger.critical(f"💾 [QUOTED SAVE] Colonia guardada: {user_response}")
                
            # Detectar preguntas sobre nombre
            elif any(keyword in quoted_lower for keyword in ['nombre', 'llamas', 'llama']):
                save_user_answer(from_number, "selection2", user_response)
                logger.critical(f"💾 [QUOTED SAVE] Nombre guardado: {user_response}")
                
            # Detectar preguntas sobre problema/tipo
            elif any(keyword in quoted_lower for keyword in ['problema', 'tipo', 'motivo', 'reporte']):
                save_user_answer(from_number, "selection4", user_response)
                logger.critical(f"💾 [QUOTED SAVE] Problema guardado: {user_response}")
        
        # Crear o actualizar sesión de reporte si es necesario
        if from_number not in report_sessions:
            create_or_update_report_session(from_number)
            logger.critical(f"🎯 [QUOTED SESSION] Sesión creada por mensaje citado")
        
        return user_response
        
    except Exception as e:
        logger.error(f"Error processing quoted message: {str(e)}")
        return text


async def complete_cleanup_after_report(phone_number, delay_seconds=5):
    """
    🧹 LIMPIEZA COMPLETA después de crear un reporte exitoso.
    Elimina TODAS las estructuras de datos relacionadas.
    
    Args:
        phone_number (str): Número de teléfono del usuario
        delay_seconds (int): Segundos a esperar para asegurar que el mensaje se envió
    """
    try:
        await asyncio.sleep(delay_seconds)
        
        logger.critical(f"🧹 [COMPLETE CLEANUP] Iniciando limpieza completa para {phone_number}")
        
        # 1. Limpiar report_sessions
        with report_sessions_lock:
            if phone_number in report_sessions:
                del report_sessions[phone_number]
                logger.critical(f"🧹 [DELETED] report_sessions[{phone_number}]")
        
        # 2. Limpiar user_answers
        if phone_number in user_answers:
            del user_answers[phone_number]
            logger.critical(f"🧹 [DELETED] user_answers[{phone_number}]")
        
        # 3. Limpiar reports_in_progress
        with reports_lock:
            if phone_number in reports_in_progress:
                del reports_in_progress[phone_number]
                logger.critical(f"🧹 [DELETED] reports_in_progress[{phone_number}]")
        
        # 4. Verificar completed_reports (mantener por un tiempo para evitar duplicados)
        if phone_number in completed_reports:
            logger.critical(f"🧹 [KEPT] completed_reports[{phone_number}] (mantener para evitar duplicados)")
        
        logger.critical(f"🧹 [COMPLETE CLEANUP] ✅ Limpieza completa terminada para {phone_number}")
        
    except Exception as e:
        logger.error(f"🧹 [ERROR] Error en limpieza completa para {phone_number}: {str(e)}")

async def delayed_cleanup_report_session(phone_number, delay_seconds=30):
    """
    Limpia la sesión de reporte después de un delay para evitar reportes duplicados por timeout.
    
    Args:
        phone_number (str): Número de teléfono del usuario
        delay_seconds (int): Segundos a esperar antes de limpiar (default: 30)
    """
    try:
        await asyncio.sleep(delay_seconds)
        
        with report_sessions_lock:
            if phone_number in report_sessions:
                del report_sessions[phone_number]
                logger.info(f"Sesión de reporte limpiada para {phone_number} después de {delay_seconds} segundos (evitar duplicados)")
                
    except Exception as e:
        logger.error(f"Error al limpiar sesión de reporte para {phone_number}: {str(e)}")

def create_or_update_report_session(from_number):
    """
    Crea o actualiza la sesión de reporte cuando se detecta actividad de reporte.
    NO requiere imágenes para iniciar la sesión.
    """
    with report_sessions_lock:
        if from_number not in report_sessions:
            report_sessions[from_number] = {
                "images": [],
                "image_descriptions": [],
                "location": None,
                "timestamp": datetime.now(pytz.timezone('America/Mexico_City')),
                "image_prompted": False,
                "image_decision": None,
                "declared_emergency": None,
            }
            logger.critical(f"🎯 [NEW SESSION] Sesión de reporte creada para {from_number}")
        else:
            # Actualizar timestamp si ya existe
            report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
            logger.critical(f"🎯 [UPDATE SESSION] Timestamp actualizado para {from_number}")


def assistant_asked_for_optional_image(message: str) -> bool:
    if not message:
        return False

    normalized = message.lower()
    patterns = [
        "deseas agregar una imagen",
        "deseas agregar imagen",
        "agregar una imagen para complementar tu reporte",
        "agregar imagen para complementar tu reporte",
        "¿deseas agregar una imagen",
        "quieres agregar una imagen",
    ]
    return any(pattern in normalized for pattern in patterns)


def assistant_asked_if_emergency(message: str) -> bool:
    if not message:
        return False

    normalized = message.lower()
    patterns = [
        "es una emergencia",
        "esto lo considerarías una emergencia",
        "esto lo considerarias una emergencia",
        "consideras que es una emergencia",
        "considerarías que es una emergencia",
    ]
    return any(pattern in normalized for pattern in patterns)


def classify_emergency_response(body: str) -> bool | None:
    if not body:
        return None

    normalized = body.strip().lower()
    if not normalized:
        return None

    yes_patterns = {
        "si",
        "sí",
        "si es",
        "sí es",
        "claro",
        "asi es",
        "así es",
        "correcto",
    }
    no_patterns = {
        "no",
        "no es",
        "negativo",
    }

    if normalized in yes_patterns:
        return True
    if normalized in no_patterns:
        return False

    return None


def classify_image_decision_response(body: str) -> str | None:
    if not body:
        return None

    normalized = body.strip().lower()
    if not normalized:
        return None

    no_patterns = [
        "no",
        "no gracias",
        "sin imagen",
        "sin foto",
        "no tengo foto",
        "no tengo imagen",
        "no deseo agregar imagen",
        "no deseo agregar una imagen",
        "prefiero no",
        "continua sin imagen",
        "continúa sin imagen",
        "sigue sin imagen",
        "no puedo tomar foto",
        "no puedo tomar una foto",
        "no puedo enviar foto",
        "no puedo enviar una foto",
        "es peligroso tomar foto",
        "es riesgoso tomar foto",
    ]

    yes_patterns = [
        "si",
        "sí",
        "si deseo",
        "sí deseo",
        "quiero agregar imagen",
        "quiero agregar una imagen",
        "te envio foto",
        "te envío foto",
        "te mando foto",
        "voy a mandar foto",
        "voy a enviar foto",
    ]

    if normalized in ("no", "sí", "si"):
        return "no" if normalized == "no" else "yes"

    if any(pattern in normalized for pattern in no_patterns):
        return "no"

    if any(pattern in normalized for pattern in yes_patterns):
        return "yes"

    return None


def is_explicit_human_handoff_request(body: str) -> bool:
    if not body:
        return False

    normalized = body.strip().lower()
    if not normalized:
        return False

    direct_phrases = [
        "agente humano",
        "asesor humano",
        "operador humano",
        "ejecutivo humano",
        "hablar con un humano",
        "hablar con humano",
        "hablar con una persona",
        "hablar con alguien",
        "quiero un humano",
        "quiero hablar con un humano",
        "quiero hablar con una persona",
        "pasame con un humano",
        "pásame con un humano",
        "pasame con humano",
        "pásame con humano",
        "pasame con una persona",
        "pásame con una persona",
        "pasame con alguien",
        "pásame con alguien",
        "pasame con un agente",
        "pásame con un agente",
        "pasame con un asesor",
        "pásame con un asesor",
        "pasame con un operador",
        "pásame con un operador",
        "pasame con un empleado",
        "pásame con un empleado",
        "me transfieres",
        "me transferes",
        "me trasfieres",
        "me transfieres con alguien",
        "me comunicas con alguien",
    ]

    if any(phrase in normalized for phrase in direct_phrases):
        return True

    person_terms = [
        "humano",
        "persona",
        "alguien",
        "agente",
        "asesor",
        "operador",
        "empleado",
        "ejecutivo",
        "representante",
    ]

    contact_verbs = [
        "transfer",
        "transfier",
        "trasfier",
        "comunic",
        "pas",
        "habl",
        "atend",
        "escal",
        "canaliz",
    ]

    has_person_term = any(term in normalized for term in person_terms)
    has_contact_verb = any(verb in normalized for verb in contact_verbs)

    return has_person_term and has_contact_verb


def is_simple_greeting(body: str) -> bool:
    if not body:
        return False

    normalized = re.sub(r"[^\w\sáéíóúñ]", " ", body.strip().lower())
    normalized = " ".join(normalized.split())
    if not normalized:
        return False

    simple_greetings = {
        "hola",
        "buenas",
        "buen día",
        "buen dia",
        "buenas tardes",
        "buenos días",
        "buenos dias",
        "buenas noches",
        "que tal",
        "qué tal",
    }
    return normalized in simple_greetings


def is_non_bot_operator(operator_id, bot_operator_ids) -> bool:
    try:
        return bool(operator_id) and int(operator_id) not in bot_operator_ids
    except (TypeError, ValueError):
        return False


def normalize_validation_block_message(message: str) -> str:
    if not message:
        return ""

    if message.startswith("VALIDATION_BLOCK:"):
        return message.replace("VALIDATION_BLOCK:", "", 1).strip()

    return message


def sanitize_outbound_phone_numbers(message: str, customer_phone: str | None = None) -> str:
    if not message:
        return message

    allowed_phone_digits = {
        "8189882000",
    }
    customer_digits = "".join(ch for ch in (customer_phone or "") if ch.isdigit())
    url_pattern = re.compile(r"https?://[^\s]+", re.IGNORECASE)
    phone_pattern = re.compile(r"(?<![\w/])(?:\+?\d[\d\-\s\(\)]{8,}\d)")

    protected_urls = []

    def protect_url(match):
        protected_urls.append(match.group(0))
        return f"__URLTOKEN_{len(protected_urls) - 1}__"

    def replace_phone(match):
        raw = match.group(0)
        digits = "".join(ch for ch in raw if ch.isdigit())

        if len(digits) < 10:
            return raw

        if customer_digits and digits.endswith(customer_digits[-10:]):
            logger.warning("📵 [SANITIZE] Ocultando teléfono del cliente en respuesta: %s", raw)
            return "[teléfono oculto]"

        if digits in allowed_phone_digits:
            return raw

        if len(digits) >= 11:
            logger.warning("📵 [SANITIZE] Ocultando teléfono no verificado en respuesta: %s", raw)
            return "[contacto disponible con Atención Ciudadana]"

        return raw

    protected_message = url_pattern.sub(protect_url, message)
    sanitized_message = phone_pattern.sub(replace_phone, protected_message)

    for index, original_url in enumerate(protected_urls):
        sanitized_message = sanitized_message.replace(f"__URLTOKEN_{index}__", original_url)

    return sanitized_message


def normalize_user_facing_response(message: str, customer_phone: str | None = None) -> str:
    normalized = normalize_validation_block_message(message or "")

    low = normalized.lower()
    if low.startswith("error: no se pudo obtener el id del mensaje"):
        normalized = "Estoy teniendo problemas técnicos para canalizarte en este momento. Por favor, intenta nuevamente."
    elif low.startswith("error: argumentos json inválidos"):
        normalized = "Estoy teniendo problemas técnicos para procesar tu solicitud. Por favor, intenta nuevamente."
    elif low.startswith("error: la función"):
        normalized = "Estoy teniendo problemas técnicos para procesar tu solicitud. Por favor, intenta nuevamente."

    normalized = normalized.replace("call_sid =", "").strip()
    normalized = sanitize_outbound_phone_numbers(normalized, customer_phone=customer_phone)
    return normalized


def resolve_fixed_security_phone_response(message: str) -> str | None:
    normalized = (message or "").strip().lower()
    if not normalized:
        return None

    asks_for_phone = any(token in normalized for token in ("telefono", "teléfono", "numero", "número"))
    if not asks_for_phone:
        return None

    if "c4" in normalized:
        return "Claro: C4 San Pedro: 81 89 88 20 00."

    if "c2" in normalized:
        return "Claro: C2 San Pedro: 81 89 88 11 00 Ext. 6011."

    if "ciac" in normalized or "atencion ciudadana" in normalized:
        return "Claro: Atención Ciudadana / CIAC: 81 84 00 44 00 Ext. 2762."

    return None


def detect_report_intent(body, response_content):
    """
    Detecta si el usuario quiere hacer un reporte basándose en keywords.
    """
    combined_text = f"{body.lower()} {response_content.lower()}"
    
    report_keywords = [
        "reporte", "reportar", "levantar reporte", "quiero reportar",
        "problema", "bache", "luminaria", "basura", "drenaje",
        "hacer reporte", "necesito reportar", "tengo un problema"
    ]
    
    return any(keyword in combined_text for keyword in report_keywords)

def should_create_report_session(body, response_content):
    """
    Determina si una conversación justifica crear una sesión de reporte.
    MUY RESTRICTIVO - solo para casos obvios de reportes.
    """
    combined_text = f"{body.lower()} {response_content.lower()}"
    
    # 🎯 PALABRAS CLAVE SUPER ESPECÍFICAS PARA REPORTES
    report_indicators = [
        "quiero reportar", "hacer un reporte", "levantar reporte", 
        "tengo un problema con", "reportar un bache", "reportar basura",
        "reportar luminaria", "hay un bache", "luz apagada", 
        "basura acumulada", "fuga de agua", "semáforo descompuesto",
        "reporte de", "problema en la calle", "hacer reporte",
        "se fue la luz", "no hay luz", "sin luz", "sin energia",
        "sin energía", "no tengo luz", "se fue la electricidad",
        "no tengo electricidad"
    ]
    
    # 🎯 PALABRAS QUE INDICAN QUE NO ES REPORTE
    non_report_indicators = [
        "calidad del aire", "información sobre", "horarios", 
        "qué puedes hacer", "ayuda", "hola", "buenos días",
        "pregunta", "cuándo", "dónde está", "cómo funciona",
        "oficina", "trámite", "registro civil"
    ]
    
    # Si hay indicadores de NO-reporte, definitivamente NO crear sesión
    if any(indicator in combined_text for indicator in non_report_indicators):
        return False
    
    # Solo crear sesión si hay indicadores claros de reporte
    return any(indicator in combined_text for indicator in report_indicators)

def normalize_selection_key(question_key):
    """Normaliza llaves legacy ('1') y canónicas ('selection1')."""
    if question_key is None:
        return None

    key = str(question_key).strip()
    if not key:
        return key

    if key.startswith("selection"):
        return key

    if key.isdigit():
        return f"selection{key}"

    return key

def save_user_answer(from_number, question_number, selection_text):
    """Guarda respuesta del usuario para una pregunta específica"""
    if from_number not in user_answers:
        user_answers[from_number] = {}
    normalized_key = normalize_selection_key(question_number)
    user_answers[from_number][normalized_key] = selection_text
    logger.debug(f"💾 [SAVE] {from_number} - {normalized_key}: {selection_text}")
    
    # 🎯 NUEVA LÍNEA: Crear sesión de reporte automáticamente
    #create_or_update_report_session(from_number)

def get_user_answer(from_number, question_number):
    """Obtiene respuesta guardada del usuario para una pregunta específica"""
    normalized_key = normalize_selection_key(question_number)
    answers = user_answers.get(from_number, {})
    legacy_key = str(question_number).strip() if question_number is not None else None
    answer = answers.get(normalized_key, "")
    if not answer and legacy_key and legacy_key != normalized_key:
        answer = answers.get(legacy_key, "")
    logger.debug(f"💾 [GET] {from_number} - {normalized_key}: {answer}")
    return answer

def build_report_state_snapshot(from_number: str) -> dict:
    session = report_sessions.get(from_number, {}) if from_number else {}
    answer_map = user_answers.get(from_number, {}) if from_number else {}
    return {
        "has_report_session": from_number in report_sessions,
        "image_prompted": session.get("image_prompted"),
        "image_decision": session.get("image_decision"),
        "declared_emergency": session.get("declared_emergency"),
        "images_count": len(session.get("images", []) or []),
        "has_location": bool(session.get("location")),
        "selection1": answer_map.get("selection1", ""),
        "selection2": answer_map.get("selection2", ""),
        "selection4": answer_map.get("selection4", ""),
        "selection5": answer_map.get("selection5", ""),
        "selection6": answer_map.get("selection6", ""),
        "selection7": answer_map.get("selection7", ""),
    }

def log_operational_decision_trace(from_number: str, stage: str, **details) -> None:
    payload = {
        "phone": from_number,
        "stage": stage,
        **details,
    }
    try:
        logger.critical("🧠 [DECISION TRACE] %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        logger.critical("🧠 [DECISION TRACE] %s", payload)

def build_outbound_response_dedup_key(from_number: str, message_id: str | int | None, response_content: str) -> str:
    normalized_text = " ".join((response_content or "").split()).strip().lower()
    digest = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()
    return f"{from_number}|{message_id}|{digest}"

async def save_client_selection2_protected(yoga_number: str, selection1: str, selection2: str, 
                                          selection3: str, selection4: str, selection5: str, 
                                          selection6: str, selection7: str, selection8: str = None, 
                                          images_list: list = None, descriptions_list: list = None):
    """
    Versión protegida contra duplicados de save_client_selection2
    """
    
    # Preparar datos para verificación
    selection_data = {
        'selection1': selection1 or "984",
        'selection2': selection2 or "Ciudadano", 
        'selection3': selection3 or "",
        'selection4': selection4 or "Sin descripción",
        'selection5': selection5 or "Sin especificar",
        'selection6': selection6 or "0000",
        'selection7': selection7 or "Sin especificar"
    }
    
    # VERIFICAR SI SE PUEDE CREAR EL REPORTE
    can_create, reason, existing_folio = dedup_manager.can_create_report(
        yoga_number, selection_data, images_list
    )
    
    if not can_create:
        logger.warning(f"🚫 [BLOCKED] Reporte bloqueado para {yoga_number}: {reason}")
        if existing_folio:
            return f"Folio: {existing_folio}"
        else:
            return f"Error: {reason}"
    
    # MARCAR INICIO DE CREACIÓN
    request_id = dedup_manager.mark_report_creation_start(yoga_number)
    
    try:
        logger.critical(f"🚀 [CREATING] Iniciando reporte {request_id}")
        
        # LLAMAR A LA FUNCIÓN ORIGINAL
        folio = await save_client_selection2(
            yoga_number=yoga_number,
            selection1=selection1,
            selection2=selection2,
            selection3=selection3,
            selection4=selection4,
            selection5=selection5,
            selection6=selection6,
            selection7=selection7,
            selection8=selection8,
            images_list=images_list,
            descriptions_list=descriptions_list
        )
        
        if folio and "Folio:" in folio:
            # MARCAR COMO EXITOSO
            dedup_manager.mark_report_creation_success(
                yoga_number, folio, selection_data, images_list
            )
            
            logger.critical(f"✅ [SUCCESS] Reporte creado: {folio} para {yoga_number}")
            return folio
        else:
            # MARCAR COMO FALLIDO
            dedup_manager.mark_report_creation_failure(yoga_number)
            logger.error(f"❌ [FAILED] Fallo al crear reporte para {yoga_number}: {folio}")
            return folio
            
    except Exception as e:
        # MARCAR COMO FALLIDO
        dedup_manager.mark_report_creation_failure(yoga_number)
        logger.error(f"💥 [ERROR] Error creando reporte para {yoga_number}: {str(e)}")
        raise


async def save_client_selection2_guarded(
    yoga_number: str,
    selection1: str,
    selection2: str,
    selection3: str,
    selection4: str,
    selection5: str,
    selection6: str,
    selection7: str,
    selection8: str = None,
    images_list: list = None,
    descriptions_list: list = None,
):
    """
    Guardar la información de las preguntas según las respuestas del cliente.
    yoga_number (string): El número de teléfono del cliente.
    selection1 (string): ID numérico del asunto (ej: "984" para baches) o "0" para auto-clasificación.
    selection2 (string): Nombre del cliente.
    selection3 (string): SIEMPRE debe ser una cadena vacía "".
    selection4 (string): Razón del reporte.
    selection5 (string): Calle.
    selection6 (string): Número (default: 000).
    selection7 (string): Colonia.
    selection8 (string, optional): URL o ruta de la imagen para la pregunta 8.
    images_list (array[string], optional): Lista de URLs de imágenes.
    descriptions_list (array[string], optional): Lista de descripciones correspondientes a las imágenes.
    """
    emergency_codes = {"891", "892", "893", "894", "895", "896", "964"}
    normalized_type = str(selection1 or "").strip()
    normalized_name = str(selection2 or "").strip().lower()
    normalized_reason = str(selection4 or "").strip().lower()
    normalized_street = str(selection5 or "").strip().lower()
    normalized_number = str(selection6 or "").strip().lower()
    normalized_colony = str(selection7 or "").strip().lower()

    if not normalized_type or normalized_type in {"0"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por tipo inválido: %s",
            yoga_number,
            selection1,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes identificar correctamente el tipo de reporte."
        )

    if not normalized_name or normalized_name in {"ciudadano", "sin especificar"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por nombre inválido: %s",
            yoga_number,
            selection2,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes obtener un nombre válido del ciudadano."
        )

    if not normalized_reason or normalized_reason in {"sin especificar"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por motivo inválido: %s",
            yoga_number,
            selection4,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes obtener el motivo o descripción del problema."
        )

    if not normalized_street or normalized_street in {"sin especificar"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por calle inválida: %s",
            yoga_number,
            selection5,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes obtener una calle válida. "
            "La calle es obligatoria."
        )

    if not normalized_number or normalized_number in {"sin especificar"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por número inválido: %s",
            yoga_number,
            selection6,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes obtener el número. "
            "Si el usuario no lo sabe o no existe numeración, usa '0000' solo en ese caso."
        )

    if not normalized_colony or normalized_colony in {"0000", "sin especificar"}:
        logger.warning(
            "🚫 [GUARD] save_client_selection2 bloqueado para %s por colonia inválida: %s",
            yoga_number,
            selection7,
        )
        return (
            "VALIDATION_BLOCK: Antes de crear el reporte, debes obtener una colonia válida. "
            "La colonia es obligatoria y no puede ser '0000'."
        )

    session = report_sessions.get(yoga_number, {})
    has_images = bool(images_list) or bool(session.get("images")) or bool(str(selection8 or "").strip())
    declared_emergency = session.get("declared_emergency") is True

    if normalized_type not in emergency_codes and not declared_emergency:
        image_prompted = bool(session.get("image_prompted"))
        image_decision = session.get("image_decision")

        if not image_prompted and not has_images and image_decision is None:
            logger.warning(
                "🚫 [GUARD] save_client_selection2 bloqueado para %s: falta preguntar imagen",
                yoga_number,
            )
            return (
                "VALIDATION_BLOCK: Antes de crear el reporte, pregunta al usuario si desea agregar "
                "una imagen para complementar su reporte. La imagen es opcional."
            )

        if image_prompted and image_decision is None and not has_images:
            logger.warning(
                "🚫 [GUARD] save_client_selection2 bloqueado para %s: falta respuesta sobre imagen",
                yoga_number,
            )
            return (
                "VALIDATION_BLOCK: Aún falta la respuesta del usuario sobre si desea agregar "
                "imagen. Debes esperar su respuesta antes de crear el reporte."
            )

    return await save_client_selection2_protected(
        yoga_number=yoga_number,
        selection1=selection1,
        selection2=selection2,
        selection3=selection3,
        selection4=selection4,
        selection5=selection5,
        selection6=selection6,
        selection7=selection7,
        selection8=selection8,
        images_list=images_list,
        descriptions_list=descriptions_list,
    )


save_client_selection2_guarded.__name__ = "save_client_selection2"

async def transfer_to_group_guarded(message_id: int, group_id: int | None = None, reason: str | None = None):
    """
    Transfiere una conversación usando el message_id del payload.

    message_id (number): ID del mensaje del payload. OBLIGATORIO.
    group_id (number, optional): Se ignora cualquier valor solicitado y se usa el grupo configurado del bot.
    reason (string, optional): Razón de la transferencia para logs.

    Returns:
        string: Mensaje de confirmación o error.
    """
    context = transfer_guard_context.get(str(message_id), {})
    explicit_handoff = bool(context.get("explicit_handoff"))
    report_intent = bool(context.get("report_intent"))
    report_state = context.get("report_state") or {}
    has_report_session = bool(report_state.get("has_report_session"))
    from_number = context.get("from_number")
    body_preview = (context.get("body") or "")[:180]
    reason_lower = (reason or "").strip().lower()
    greeting_only = is_simple_greeting(context.get("body") or "")
    stale_explicit_handoff_reason = (
        not explicit_handoff and
        any(
            marker in reason_lower
            for marker in (
                "solicita hablar con un agente humano",
                "solicita hablar con humano",
                "hablar con un agente humano",
                "hablar con humano",
            )
        )
    )

    logger.critical(
        "🔀 [TRANSFER GUARD] message_id=%s requested_group_id=%s reason=%s explicit_handoff=%s report_intent=%s has_report_session=%s greeting_only=%s stale_explicit_handoff_reason=%s from_number=%s body=%s",
        message_id,
        group_id,
        reason,
        explicit_handoff,
        report_intent,
        has_report_session,
        greeting_only,
        stale_explicit_handoff_reason,
        from_number,
        body_preview,
    )

    if not explicit_handoff and (
        report_intent or
        has_report_session or
        greeting_only or
        stale_explicit_handoff_reason
    ):
        logger.critical(
            "⛔ [TRANSFER BLOCKED] message_id=%s from_number=%s reason=%s report_intent=%s has_report_session=%s greeting_only=%s stale_explicit_handoff_reason=%s",
            message_id,
            from_number,
            reason,
            report_intent,
            has_report_session,
            greeting_only,
            stale_explicit_handoff_reason,
        )
        return (
            "Error: transferencia bloqueada por guardia local. "
            "Continua atendiendo el reporte con el flujo normal y no transfieras a humano "
            "a menos que el usuario lo solicite explícitamente."
        )

    return await transfer_to_group(
        message_id=message_id,
        group_id=group_id,
        reason=reason,
    )


transfer_to_group_guarded.__name__ = "transfer_to_group"

def clear_user_answers(from_number):
    """Limpia todas las respuestas guardadas de un usuario"""
    if from_number in user_answers:
        del user_answers[from_number]
        logger.debug(f"💾 [CLEAR] Datos eliminados para {from_number}")

def get_auto_finalization_status(from_number):
    """
    Obtiene información sobre el estado de auto-finalización de un número.
    
    Returns:
        dict: Información del estado
    """
    if from_number not in report_sessions:
        return {"status": "no_session", "message": "No hay sesión de reporte activa"}
    
    session = report_sessions[from_number]
    now = datetime.now(pytz.timezone('America/Mexico_City'))
    elapsed = (now - session["timestamp"]).total_seconds()
    remaining = 10 - elapsed  # 5 minutos = 300 segundos
    
    has_complete_data = has_complete_report_data(from_number)
    has_images = bool(session["images"])
    
    return {
        "status": "active",
        "elapsed_minutes": elapsed / 60,
        "remaining_minutes": max(0, remaining / 60),
        "has_complete_data": has_complete_data,
        "has_images": has_images,
        "will_auto_finalize": has_complete_data and has_images and remaining <= 0,
        "image_count": len(session["images"]),
        "last_activity": session["timestamp"].isoformat()
    }

def has_complete_report_data(from_number):
    """
    Verifica si un usuario tiene todos los datos necesarios para generar un reporte.
    
    Args:
        from_number (str): Número de teléfono del usuario
        
    Returns:
        bool: True si tiene todos los datos necesarios, False en caso contrario
    """
    try:
        # Obtener todos los datos guardados del usuario
        selection1 = get_user_answer(from_number, "selection1")  # Tipo de reporte
        selection2 = get_user_answer(from_number, "selection2")  # Nombre
        selection4 = get_user_answer(from_number, "selection4")  # Razón del reporte
        selection5 = get_user_answer(from_number, "selection5")  # Calle
        selection6 = get_user_answer(from_number, "selection6")  # Número
        selection7 = get_user_answer(from_number, "selection7")  # Colonia
        
        # Verificar que tenga al menos los campos esenciales
        essential_fields = [selection2, selection4, selection5, selection7]  # Nombre, razón, calle, colonia
        
        # Contar campos completados
        completed_fields = sum(1 for field in essential_fields if field and field.strip())
        
        # También verificar si tiene imágenes
        has_images = (from_number in report_sessions and 
                     report_sessions[from_number]["images"] and 
                     len(report_sessions[from_number]["images"]) > 0)
        
        # Considerar completo si tiene al menos 3 de los 4 campos esenciales Y tiene imágenes
        is_complete = completed_fields >= 3 and has_images
        
        logger.debug(f"[{from_number}] Verificación de datos completos: "
                    f"campos={completed_fields}/4, imágenes={has_images}, completo={is_complete}")
        
        return is_complete
        
    except Exception as e:
        logger.error(f"Error verificando datos completos para {from_number}: {str(e)}")
        return False

async def remove_from_recently_returned(number, delay_seconds):
    """Remove a number from recently_returned_to_bot after a delay."""
    try:
        await asyncio.sleep(delay_seconds)
        if number in recently_returned_to_bot:
            del recently_returned_to_bot[number]
            logger.info(f"Removed {number} from recently returned to bot tracking")
        if number in bot_returned_at:
            del bot_returned_at[number]
            logger.info(f"Removed {number} from bot_returned_at tracking")
    except Exception as e:
        logger.error(f"Error removing {number} from recently returned tracking: {str(e)}")

def has_recent_report(phone_number, max_age_minutes=15):
    """
    Verifica si un número tiene un reporte creado recientemente.
    
    Args:
        phone_number (str): Número de teléfono a verificar
        max_age_minutes (int): Tiempo máximo en minutos para considerar un reporte como "reciente"
        
    Returns:
        dict: None si no hay reporte reciente, o información del reporte si existe
    """
    if phone_number not in completed_reports:
        return None
    
    # Verificar si el reporte es reciente
    report_info = completed_reports[phone_number]
    current_time = datetime.now().timestamp()
    elapsed_minutes = (current_time - report_info['timestamp']) / 60
    
    if elapsed_minutes <= max_age_minutes:
        return report_info
    
    # Si el reporte es antiguo, eliminarlo del registro y retornar None
    del completed_reports[phone_number]
    return None


# Añade esta función wrapper alrededor de save_client_selection
async def save_client_selection_with_deduplication(yoga_number, selection1, selection2, selection3,
                                       selection4, selection5, selection6, selection7, 
                                       selection8=None, images_list=None, descriptions_list=None):
    """
        Wrapper around save_client_selection2 for report deduplication.
    
    Args:
        yoga_number (str): Phone number
        selection1 (str): Asunto ID (e.g., "984" for baches)
        selection2 (str): Name of the reporter
        selection3 (str): Always empty string ""
        selection4 (str): Report description
        selection5 (str): Street name
        selection6 (str): Street number (default"0000")
        selection7 (str): Neighborhood name
        selection8 (str, optional): Legacy parameter (not used)
        images_list (list, optional): List of image URLs
        descriptions_list (list, optional): List of image descriptions
        
    Returns:
        str: Report folio number
    """
    # Verificar si ya existe un reporte reciente para este número
    recent_report = has_recent_report(yoga_number)
    if recent_report:
        logger.warning(f"Evitando reporte duplicado para {yoga_number}. Folio existente: {recent_report['folio']}")
        return recent_report['folio']  # Retornar el folio del reporte existente
    
    # Si no hay reporte reciente, proceder con la creación
    try:
        if not selection1 or not selection1.isdigit():
            selection1 = "984"

        if not selection2:
            selection2 = "Ciudadano"

        selection3 = ""
        logger.debug(f"Creating report with params: asunto={selection1}, name={selection2}, " +
                   f"desc={selection4}, calle={selection5}, numero={selection6}, colonia={selection7}")
        logger.debug(f"Images: {len(images_list) if images_list else 0}")

        folio = await save_client_selection2(
            yoga_number=yoga_number, 
            selection1=selection1, 
            selection2=selection2, 
            selection3=selection3,
            selection4=selection4, 
            selection5=selection5, 
            selection6=selection6, 
            selection7=selection7,
            selection8=selection8, 
            images_list=images_list,  # Asegúrate de que este parámetro se pase
            descriptions_list=descriptions_list
        )
        
        # Registrar este reporte exitoso
        completed_reports[yoga_number] = {
            'timestamp': datetime.now().timestamp(),
            'folio': folio
        }
        
        # Programar eliminación del registro después de cierto tiempo (e.g., 30 minutos)
        asyncio.create_task(remove_from_completed_reports(yoga_number, 1800))
        
        return folio
    except Exception as e:
        logger.error(f"Error al crear reporte para {yoga_number}: {str(e)}")
        raise


# Using OrderedDict as a simple TTL cache
class TTLCache:
    def __init__(self, max_size=1000, ttl_seconds=3600):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def add(self, key):
        # Clean expired entries first
        self._clean_expired()
        
        # Add new entry with timestamp
        self.cache[key] = datetime.now()
        
        # If over size limit, remove oldest
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def contains(self, key):
        if key not in self.cache:
            return False
        
        # Check if expired
        timestamp = self.cache[key]
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self.cache[key]
            return False
        
        return True
    
    def _clean_expired(self):
        # Remove expired entries
        now = datetime.now()
        expired_keys = [k for k, v in self.cache.items() 
                       if now - v > timedelta(seconds=self.ttl_seconds)]
        for key in expired_keys:
            del self.cache[key]

    def remove(self, key):
        self.cache.pop(key, None)
    
    # Add this method to support len()
    def __len__(self):
        self._clean_expired()  # Clean expired entries first
        return len(self.cache)

async def analyze_image_with_rate_limit(client, photo_url):
    """
    Analyze an image with rate limiting to prevent API overload.
    
    Args:
        client: OpenAI client instance
        photo_url: URL of the image to analyze
        
    Returns:
        str: Image description from the analysis
    """
    try:
        logger.debug(f"Starting rate-limited image analysis for: {photo_url}")
        
        # Download the image with timeout
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url, timeout=10) as response:
                response.raise_for_status()
                image_content = BytesIO(await response.read())
        
        # Rate-limited OpenAI API call
        async def _analyze_with_openai():
            image_analysis = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe esta imagen en una frase breve (máximo 15 palabras)."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_content.getvalue()).decode('utf-8')}",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=100,
            )
            return image_analysis.choices[0].message.content
            
        # Use the queue to process with rate limiting
        description = await image_processing_queue.add_task(_analyze_with_openai)
        return description
        
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return f"Error al analizar la imagen: {str(e)}"
    
async def manage_message_history(db, number, max_messages=20):
    """
    Mantiene solo los últimos max_messages mensajes para un número dado
    """
    try:
        # Contar cuántos mensajes tiene este número
        conn = psycopg2.connect(dbname=db.dbName, user=db.user, password=db.password, host=db.host, port=db.port)
        cursor = conn.cursor()
        
        # Contar mensajes
        cursor.execute("SELECT COUNT(*) FROM messages WHERE number = %s", [number])
        count = cursor.fetchone()[0]
        
        # Si hay más mensajes que el máximo permitido, eliminar los más antiguos
        if count > max_messages:
            # Obtener los IDs de los mensajes más antiguos que exceden el límite
            cursor.execute("""
                DELETE FROM messages 
                WHERE id IN (
                    SELECT id FROM messages 
                    WHERE number = %s 
                    ORDER BY time ASC 
                    LIMIT %s
                )
            """, [number, count - max_messages])
            
            deleted_count = cursor.rowcount
            logger.debug(f"Se eliminaron {deleted_count} mensajes antiguos para mantener el límite de {max_messages} para {number}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error al gestionar historial de mensajes: {str(e)}")

async def check_report_timeouts():
    """
    🎯 VERSIÓN MEJORADA: Con limpieza completa inmediata después de crear reportes
    y manejo robusto de errores para evitar crashes silenciosos.
    """
    while True:
        try:
            await asyncio.sleep(60)  # Revisar cada minuto
            now = datetime.now(pytz.timezone('America/Mexico_City'))

            logger.critical(f"🔍 [TIMEOUT] Revisando sesiones activas: {len(report_sessions)}")

            numbers_to_process = []

            with report_sessions_lock:
                for number, session in list(report_sessions.items()):
                    try:
                        elapsed = (now - session["timestamp"]).total_seconds()
                        images_count = len(session.get("images", []))
                        
                        # Verificar si tiene datos completos con manejo de errores
                        street = get_user_answer(number, "selection5")
                        try:
                            street_valid, street_msg = validate_street_exists(street) if street else (False, "Sin calle")
                        except Exception as e:
                            logger.error(f"💥 [VALIDATION ERROR] Error validando calle para {number}: {str(e)}")
                            street_valid, street_msg = False, f"Error validando calle: {str(e)}"

                        colony = get_user_answer(number, "selection7")
                        try:
                            colony_valid, colony_msg = validate_colony_exists(colony) if colony else (False, "Sin colonia")
                        except Exception as e:
                            logger.error(f"💥 [VALIDATION ERROR] Error validando colonia para {number}: {str(e)}")
                            colony_valid, colony_msg = False, f"Error validando colonia: {str(e)}"
                        
                        problem = get_user_answer(number, "selection4")
                        name = get_user_answer(number, "selection2")

                        has_complete_data = (
                            name and len(name.strip()) >= 2 and
                            problem and len(problem.strip()) > 5 and
                            (street_valid or colony_valid)  # Calle válida O colonia válida
                        )

                        logger.critical(f"🔍 [VALIDATION] {number}: calle_válida={street_valid} ({street_msg}), "
                                    f"colonia_válida={colony_valid} ({colony_msg}), completo={has_complete_data}")
                        
                        logger.critical(f"🔍 [TIMEOUT] {number}: {elapsed:.1f}s inactivo, {images_count} imágenes, datos_completos={has_complete_data}")
                        
                        # Procesar si cumple timeout Y tiene datos suficientes
                        if elapsed > 420:  # 7 minutos
                            if images_count > 0 or has_complete_data:
                                logger.critical(f"⏰ [7MIN TIMEOUT] {number} será procesado")
                                numbers_to_process.append(number)
                            else:
                                # Sin datos suficientes, solo limpiar
                                logger.critical(f"🗑️ [CLEANUP] {number} sin datos suficientes, eliminando sesión")
                                try:
                                    del report_sessions[number]
                                    if number in user_answers:
                                        del user_answers[number]
                                except Exception as e:
                                    logger.error(f"💥 [CLEANUP ERROR] Error limpiando {number}: {str(e)}")
                                    
                    except Exception as e:
                        logger.error(f"💥 [SESSION ERROR] Error procesando sesión {number}: {str(e)}")
                        logger.error(f"💥 [SESSION ERROR] Traceback: {traceback.format_exc()}")
                        continue
            
            # Procesar cada número que cumplió timeout
            for number in numbers_to_process:
                try:
                    logger.critical(f"⏰ [EJECUTANDO] Creando reporte automático para {number}")

                    # 🚫 VERIFICAR DUPLICADOS PRIMERO
                    try:
                        recent_report = has_recent_report(number, max_age_minutes=15)
                        if recent_report:
                            logger.critical(f"🚫 [DUPLICATE PREVENTION] {number} ya tiene reporte reciente: {recent_report['folio']}")
                            
                            # 🧹 LIMPIEZA INMEDIATA de duplicado detectado
                            asyncio.create_task(complete_cleanup_after_report(number, 1))
                            continue  # Saltar al siguiente número
                    except Exception as e:
                        logger.error(f"💥 [DUPLICATE CHECK ERROR] Error verificando duplicados para {number}: {str(e)}")
                    
                    # Verificar que la sesión aún exista
                    with report_sessions_lock:
                        if number not in report_sessions:
                            logger.warning(f"⏰ [SKIP] Sesión {number} ya no existe")
                            continue
                        
                        session = report_sessions[number]
                        images = session.get("images", [])
                        descriptions = session.get("image_descriptions", [])

                    # Recuperar datos guardados con valores por defecto seguros
                    try:
                        saved_selection1 = get_user_answer(number, "selection1") or "984"
                        saved_selection2 = get_user_answer(number, "selection2") or "Ciudadano"
                        saved_selection4 = get_user_answer(number, "selection4") or "Reporte automático por timeout"
                        saved_selection5 = get_user_answer(number, "selection5") or "Sin especificar"
                        saved_selection6 = get_user_answer(number, "selection6") or "0000"
                        saved_selection7 = get_user_answer(number, "selection7") or "Sin especificar"
                    except Exception as e:
                        logger.error(f"💥 [DATA ERROR] Error obteniendo datos para {number}: {str(e)}")
                        # Usar valores por defecto seguros
                        saved_selection1 = "984"
                        saved_selection2 = "Ciudadano"
                        saved_selection4 = "Reporte automático por timeout (error en datos)"
                        saved_selection5 = "Sin especificar"
                        saved_selection6 = "0000"
                        saved_selection7 = "Sin especificar"
                    
                    logger.critical(f"⏰ [DATOS] {number}: tipo={saved_selection1}, nombre={saved_selection2}, desc={saved_selection4}")
                    
                    # Crear el reporte con manejo de errores
                    try:
                        folio = await save_client_selection2_guarded(
                            yoga_number=number,
                            selection1=saved_selection1,
                            selection2=saved_selection2,
                            selection3="",
                            selection4=saved_selection4,
                            selection5=saved_selection5,
                            selection6=saved_selection6,
                            selection7=saved_selection7,
                            selection8=",".join(images) if images else "",
                            images_list=images,
                            descriptions_list=descriptions
                        )
                        
                        if isinstance(folio, str) and folio.startswith("Folio:"):
                            # 💾 Registrar en completed_reports para evitar duplicados futuros
                            completed_reports[number] = {
                                'timestamp': datetime.now().timestamp(),
                                'folio': folio
                            }
                            logger.critical(f"💾 [REGISTER] Reporte registrado en completed_reports: {folio}")
                            
                            logger.critical(f"✅ [SUCCESS] Reporte automático creado: {folio} para {number}")

                            # 📤 Notificar al usuario
                            try:
                                await notify_user_timeout_flexible(number, folio, len(images))
                            except Exception as e:
                                logger.error(f"💥 [NOTIFICATION ERROR] Error notificando a {number}: {str(e)}")
                            
                            # 🧹 LIMPIEZA COMPLETA INMEDIATA
                            asyncio.create_task(complete_cleanup_after_report(number, 5))
                            
                            logger.critical(f"✅ [TIMEOUT COMPLETE] Proceso completo para {number}")
                        elif isinstance(folio, str) and folio.startswith("VALIDATION_BLOCK:"):
                            logger.warning(f"🚫 [TIMEOUT BLOCKED] Reporte automático bloqueado para {number}: {folio}")
                            asyncio.create_task(complete_cleanup_after_report(number, 1))
                        else:
                            logger.error(f"💥 [FOLIO ERROR] Resultado inválido para {number}: {folio}")
                            asyncio.create_task(complete_cleanup_after_report(number, 1))
                            
                    except Exception as e:
                        logger.error(f"💥 [SAVE ERROR] Error creando reporte para {number}: {str(e)}")
                        logger.error(f"💥 [SAVE ERROR] Traceback: {traceback.format_exc()}")
                        # En caso de error, también hacer limpieza
                        asyncio.create_task(complete_cleanup_after_report(number, 1))
                        
                except Exception as e:
                    logger.error(f"💥 [PROCESSING ERROR] Error procesando timeout para {number}: {str(e)}")
                    logger.error(f"💥 [PROCESSING ERROR] Traceback: {traceback.format_exc()}")
                    # Intentar limpieza incluso si hay error
                    try:
                        asyncio.create_task(complete_cleanup_after_report(number, 1))
                    except Exception as cleanup_error:
                        logger.error(f"💥 [CLEANUP ERROR] Error en limpieza para {number}: {str(cleanup_error)}")
                        
        except Exception as e:
            logger.error(f"💥 [TIMEOUT LOOP ERROR] Error crítico en check_report_timeouts: {str(e)}")
            logger.error(f"💥 [TIMEOUT LOOP ERROR] Traceback: {traceback.format_exc()}")
            # Continuar el loop incluso si hay error crítico
            continue

def has_complete_report_data_flexible(from_number):
    """
    🎯 VERSIÓN FLEXIBLE: Verifica si tiene datos mínimos necesarios
    AUNQUE NO TENGA IMÁGENES
    """
    try:
        selection2 = get_user_answer(from_number, "selection2")  # Nombre
        selection4 = get_user_answer(from_number, "selection4")  # Razón del reporte
        selection5 = get_user_answer(from_number, "selection5")  # Calle
        selection7 = get_user_answer(from_number, "selection7")  # Colonia
        
        # Campos mínimos requeridos: nombre, problema, calle, colonia
        essential_fields = [selection2, selection4, selection5, selection7]
        completed_fields = sum(1 for field in essential_fields if field and field.strip())
        
        # 🎯 NUEVA LÓGICA: Es completo si tiene 3 de 4 campos esenciales
        # NO requiere imágenes obligatoriamente
        is_complete = completed_fields >= 3
        
        logger.debug(f"[{from_number}] Verificación datos flexibles: "
                    f"campos={completed_fields}/4, completo={is_complete}")
        
        return is_complete
        
    except Exception as e:
        logger.error(f"Error verificando datos para {from_number}: {str(e)}")
        return False

async def notify_user_timeout(phone_number, folio, image_count):
    """
    Función BÁSICA para notificar al usuario que se creó reporte por inactividad.
    Versión simple sin muchos detalles.
    """
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        
        # Buscar cliente
        search_url = "https://api.chat2desk.com.mx/v1/clients"
        params = {"phone": phone_number}
        headers = {"Authorization": api_token, "Content-Type": "application/json"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success" and response_data.get("data"):
                client_id = response_data["data"][0]["id"]
                
                # Mensaje básico simple
                folio_clean = folio.replace("Folio: ", "") if folio.startswith("Folio: ") else folio
                message = f"Se creó por inactividad tu reporte con folio {folio_clean}"
                
                # Enviar mensaje
                message_data = {
                    "client_id": client_id,
                    "channel_id": 43906,
                    "transport": "wa_direct", 
                    "text": message
                }
                
                async with httpx.AsyncClient() as client:
                    await client.post("https://api.chat2desk.com.mx/v1/messages", 
                                    json=message_data, headers=headers)
                    
                logger.critical(f"📤 [MENSAJE ENVIADO] '{message}' enviado a {phone_number}")
                    
    except Exception as e:
        logger.error(f"Error notificando reporte por inactividad: {str(e)}")

async def notify_user_timeout_flexible(phone_number, folio, image_count):
    """Notifica con mensaje apropiado según si tiene imágenes o no"""
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        
        search_url = "https://api.chat2desk.com.mx/v1/clients"
        params = {"phone": phone_number}
        headers = {"Authorization": api_token, "Content-Type": "application/json"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success" and response_data.get("data"):
                client_id = response_data["data"][0]["id"]
                
                folio_clean = folio.replace("Folio: ", "") if folio.startswith("Folio: ") else folio
                
                if image_count > 0:
                    message = "🚀 ¡Tu reporte ya está listo!\n"
                    message += f"✅ Folio: *{folio_clean}*\n"
                    message += "📌 Debido a la inactividad, hemos generado tu folio automáticamente para que puedas continuar reportando, estamos para servirte."
                else:
                    message = "🚀 ¡Tu reporte ya está listo!\n"
                    message += f"✅ Folio: *{folio_clean}*\n"
                    message += "📌 Debido a la inactividad, hemos generado tu folio automáticamente para que puedas continuar reportando, estamos para servirte."
                
                message_data = {
                    "client_id": client_id,
                    "channel_id": 43906,
                    "transport": "wa_direct", 
                    "text": message
                }
                
                async with httpx.AsyncClient() as client:
                    await client.post("https://api.chat2desk.com.mx/v1/messages", 
                                    json=message_data, headers=headers)
                    
                logger.critical(f"📤 [MENSAJE ENVIADO] '{message}' enviado a {phone_number}")
                    
    except Exception as e:
        logger.error(f"Error notificando timeout flexible: {str(e)}")

# Función auxiliar mejorada para notificación
async def send_timeout_notification_with_real_data(phone_number, folio, image_count, sender_name, calle, colonia):
    """
    Función COMPLETA que incluye todos los datos del usuario.
    Versión más detallada con información del contexto LLM.
    """
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        
        # Buscar cliente
        search_url = "https://api.chat2desk.com.mx/v1/clients"
        params = {"phone": phone_number}
        headers = {"Authorization": api_token, "Content-Type": "application/json"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success" and response_data.get("data"):
                client_id = response_data["data"][0]["id"]
                
                # 🎯 MENSAJE SÚPER DETALLADO con todos los datos
                message = f"⏰ **Hola {sender_name}!**\n\n"
                message += f"Tu reporte se creó automáticamente por inactividad:\n\n"
                message += f"📋 **Folio:** {folio}\n"
                message += f"📸 **Imágenes:** {image_count}\n"
                message += f"🏠 **Calle:** {calle}\n"
                message += f"🏘️ **Colonia:** {colonia}\n\n"
                message += f"Si necesitas agregar más detalles, puedes contactar a atención ciudadana con tu número de folio.\n\n"
                message += f"¡Gracias por tu reporte!"
                
                # Enviar mensaje
                message_data = {
                    "client_id": client_id,
                    "channel_id": 43906,  # Canal fijo
                    "transport": "wa_direct",
                    "text": message
                }
                
                async with httpx.AsyncClient() as client:
                    await client.post("https://api.chat2desk.com.mx/v1/messages", 
                                    json=message_data, headers=headers)
                    
    except Exception as e:
        logger.error(f"Error en send_timeout_notification_with_real_data: {str(e)}")
        raise

router = APIRouter()
# Historial en memoria para una conversación dinámica
user_histories = {}

@router.post("/")
async def post(request: Request):
    response = VoiceResponse()
    host = request.headers.get("host")
    connect = Connect()
    connect.stream(url=f"wss://{host}/stream")
    response.append(connect)
    text = response.to_xml()
    logger.debug(text)
    return Response(content=text, media_type="text/xml")


@router.websocket("/stream")
async def websocket_endpoint(ws: WebSocket):
    db = LocalStorage()
    config = { conf.name: conf.getval() for conf in db.GetAll(Config) }

    logHandler = get_thread_log_handler(config.get("rawLogs", 10))

    logger.info("Got new INCOMING_CALL")

    websocket_handler = WebSocketHandler(ws)
    await websocket_handler.connect()

    # Set up Deepgram as the Speech-to-Text (STT) Model
    #stt_service = DeepgramService(DEEPGRAM_API_KEY)


    # Set up Amazon Transcribe as the Speech-to-Text (STT) Model.
    logger.debug("Setting up transcription service")
    stt_service = AmazonTranscribeService(
        region="us-east-1",
        sample_rate=8000,
        enhanced=False,
        language=config["language"]
    )

    function_manager = FunctionManager(registered_functions)

    # Get the current date and time
    now = datetime.now()
    callDirection = "Inbound"
    call = db.Search(Call(callUid = websocket_handler.call_sid), True)
    if call:
        callDirection = "Outbound"
        call.callStatus = "IN_PROGRESS"
        db.Update(call)
    else:
        call = Call(
            callTime = now.strftime("%Y-%m-%d %H:%M:%S"),
            callSource = "Twillio",
            callType = "IP",
            callDirection = "IN_COMING",
            callStatus = "IN_PROGRESS",
            callNumber = "Not Available",
            callUid = websocket_handler.call_sid
        )
        call = db.Insert(call)

    mexico_tz = pytz.timezone('America/Mexico_City')
    current_datetime = datetime.now(mexico_tz)
    print(f"Hora original (MX): {current_datetime.strftime('%Y-%m-%d %I:%M:%S %p')}")
    date_string = current_datetime.strftime("%Y-%m-%d")
    hour = current_datetime.strftime("%I:%M:%S %p")
    print(f"\nRESULTADO FINAL -> Fecha: {date_string}, Hora: {hour}")

    # Get call SID and customer identity
    call_sid = websocket_handler.call_sid
    customer_identity = await get_customer_identity(call_sid)
    call.callerName = customer_identity

    selection1 = await find_row_and_update_selection(call.callNumber, 1)
    selection2 = await find_row_and_update_selection(call.callNumber, 2)
    selection3 = await find_row_and_update_selection(call.callNumber, 3)
    selection4 = await find_row_and_update_selection(call.callNumber, 4)
    selection5 = await find_row_and_update_selection(call.callNumber, 5)
    selection6 = await find_row_and_update_selection(call.callNumber, 6)
    selection7 = await find_row_and_update_selection(call.callNumber, 7)

    #folio = await save_client_selection(call_sid, selection1, selection2, selection3, selection4, selection5, selection6, selection7)

    logger.debug("Initializing LLM service for the new call")
    llm_service = OpenAIService(
        config=config,
        api_key=OPENAI_API_KEY,
        system=system_message.format(
            customer_name=customer_identity, 
            call_sid=call_sid, 
            date2=date_string, 
            now=hour, 
            folio="folio"),
        function_manager=function_manager
    )
    
    # Alternative DeepSeek service
    # deepseek_service = DeepSeekService(
    #     config=config,
    #     api_key=os.getenv("DEEPSEEK_API_KEY"),
    #     system=system_message.format(
    #         customer_name=customer_identity, 
    #         call_sid=call_sid, 
    #         date2=date_string, 
    #         now=hour, 
    #         folio="folio"),
    #     function_manager=function_manager
    # )

    # tts_service = ElevenTTSService(
    #     api_key=ELEVENLABS_API_KEY,
    #     voice_id=VOICE_ID,
    #     similarity_boost=0.6,
    #     stability=0.7,
    #     stream_results=True,
    # )

    logger.debug("Initializing TTS engine for call")
    tts_service = AmazonTTSService(
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
        stream_results=False,
        language=config["language"]
    )

    logger.debug("Initializing orchestrator for the call")
    orchestrator = Orchestrator(
        config=config,
        websocket_handler=websocket_handler,
        stt_service=stt_service,
        llm_service=llm_service,
        tts_service=tts_service,
    )

    logger.debug("Starting a conversation with caller")
    stats = await orchestrator.process_audio_stream()

    # Sync the call record in case of AMD detection event was triggered
    call = db.Search(Call(callUid = websocket_handler.call_sid), True)
    call.callLogs = logHandler.stream.getvalue()

    if config.get(f"saveScript{callDirection}", False):
        call.callScript = json.dumps(stats['Script'])
    
    if config.get(f"recordCalls{callDirection}", False):
        call.callPlayback = json.dumps(websocket_handler.audio_sequence)
    
    if call.callStatus != "AMD":
        # (VERY IMPORTANT) only update status if AMD is not detected
        call.callStatus = stats['Status']

    call.callDuration = (datetime.now() - now).seconds
    db.Update(call)
    
    hooks = Hooks()
    for hook in hooks.Get(True):
        if hook["type"] == "POST_CALL":
            logger.debug("Hook found for call executing function " + hook["name"])
            hook["function"](call, config)

    cleanup_call_logger()

# Diccionario global para almacenar las sesiones de WhatsApp.
# En vez de user_histories, usamos user_sessions para incluir la marca de última actividad.
user_sessions = {}  # key: from_number, value: WhatsAppSession

# Tiempo de inactividad (en segundos) antes de desconectar la sesión (5 minutos)
INACTIVITY_THRESHOLD = 15 * 60

class WhatsAppSession:
    def __init__(self, history):
        self.history = history
        self.last_active = datetime.now(pytz.timezone('America/Mexico_City'))
        self.evaluation_state = None
        self.evaluation_folio = None
        self.last_hsm_time = None 
    
    def update_activity(self):
        self.last_active = datetime.now(pytz.timezone('America/Mexico_City'))

async def check_inactivity():
    """
    Tarea en background que revisa cada minuto las sesiones activas.
    Si alguna sesión ha estado inactiva más de 5 minutos, se envía un mensaje
    de alerta por Chat2Desk, elimina los mensajes de la base de datos y elimina la sesión.
    """
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        now = datetime.now(pytz.timezone('America/Mexico_City'))
        db = LocalStorage()
        
        for number, session in list(user_sessions.items()):
            elapsed = (now - session.last_active).total_seconds()
            if elapsed > INACTIVITY_THRESHOLD:
                try:
                    # 🆕 VERIFICAR SI HAY EVALUACIÓN PENDIENTE
                    if (hasattr(session, 'evaluation_state') and 
                        session.evaluation_state and
                        hasattr(session, 'evaluation_folio')):
                        
                        folio = session.evaluation_folio
                        
                        # 🆕 SI YA FUE EVALUADO, NO REENVIAR
                        if folio in evaluated_reports:
                            logger.critical(f"🚫 [INACTIVITY] Reporte {folio} ya fue evaluado, limpiando sesión")
                            session.evaluation_state = None
                            session.evaluation_folio = None
                            session.last_hsm_time = None
                            # Continuar con limpieza normal de inactividad
                        else:
                            logger.critical(f"⏰ [INACTIVITY] Evaluación pendiente para reporte {folio}, manteniendo sesión")
                            # NO limpiar la sesión si hay evaluación pendiente sin completar
                            continue

                    # Notificar al usuario usando Chat2Desk
                    api_token = os.getenv("CHAT2DESK_API_TOKEN")
                    chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                    
                    # Buscar cliente en Chat2Desk para obtener client_id
                    search_url = "https://api.chat2desk.com.mx/v1/clients"
                    params = {"phone": number}
                    
                    headers = {
                        "Authorization": api_token,
                        "Content-Type": "application/json"
                    }
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.get(search_url, params=params, headers=headers)
                    
                    if response.status_code == 200:
                        client_data = response.json()
                        if client_data.get("status") == "success" and client_data.get("data"):
                            client_id = client_data["data"][0]["id"]
                            channel_id = 43906  # Canal fijo para WhatsApp
                            
                            # Enviar mensaje de desconexión
                            message_data = {
                                "client_id": client_id,
                                "channel_id": channel_id,
                                "transport": "wa_direct",
                                "text": "Parece que te ausentaste. La conversación se cerró por inactividad. Mándanos un mensaje para comenzar de nuevo. ¡Aquí estaremos!😊"
                            }
                            
                            async with httpx.AsyncClient() as client:
                                await client.post(chat2desk_url, json=message_data, headers=headers)

                            if number in transferred_numbers:
                                del transferred_numbers[number]
                                logger.critical(f"🧹 [INACTIVITY] Eliminado {number} de transferred_numbers por inactividad")
                    
                    # Eliminar todos los mensajes de este número de la base de datos
                    conn = psycopg2.connect(dbname=db.dbName, user=db.user, password=db.password, host=db.host, port=db.port)
                    cursor = conn.cursor()
                    
                    # SQL directo para eliminar mensajes por número
                    cursor.execute("DELETE FROM messages WHERE number = %s", [number])
                    count = cursor.rowcount
                    
                    conn.commit()
                    conn.close()
                    
                    logger.debug(f"Se eliminaron {count} mensajes para el número {number} por inactividad.")
                    
                    # Eliminar la sesión
                    del user_sessions[number]
                    # Eliminar también cualquier reporte en progreso
                    if number in report_sessions:
                        del report_sessions[number]

                    # 🚫 MARCAR NÚMERO COMO CERRADO POR INACTIVIDAD
                    # SOLO si NO estaba transferido a un agente humano
                    was_transferred = number in transferred_numbers
                    if not was_transferred:
                        closed_by_inactivity[number] = datetime.now().timestamp() + INACTIVITY_COOLDOWN
                        logger.critical(f"🚫 [INACTIVITY] {number} marcado como cerrado - cooldown de {INACTIVITY_COOLDOWN/60:.0f} minutos")
                    else:
                        logger.critical(f"✅ [INACTIVITY] {number} estaba transferido, NO se aplica cooldown")

                    logger.debug(f"Sesión de {number} desconectada por inactividad.")
                except Exception as e:
                    logger.error(f"Error enviando mensaje de desconexión para {number}: {str(e)}")
                    # Aún intentamos eliminar la sesión incluso si falló el envío del mensaje
                    if number in user_sessions:
                        del user_sessions[number]
                    if number in report_sessions:
                        del report_sessions[number]

                    # Verificar si estaba transferido antes de eliminarlo
                    was_transferred = number in transferred_numbers
                    if number in transferred_numbers:
                        del transferred_numbers[number]
                        logger.critical(f"🧹 [INACTIVITY ERROR] Eliminado {number} de transferred_numbers por error")

                    # 🚫 TAMBIÉN MARCAR EN CASO DE ERROR
                    # SOLO si NO estaba transferido
                    if not was_transferred:
                        closed_by_inactivity[number] = datetime.now().timestamp() + INACTIVITY_COOLDOWN
                        logger.critical(f"🚫 [INACTIVITY ERROR] {number} marcado como cerrado (error handler)")
                    else:
                        logger.critical(f"✅ [INACTIVITY ERROR] {number} estaba transferido, NO se aplica cooldown")


async def cleanup_hsm_reports():
    """Limpia reportes HSM antiguos cada hora"""
    while True:
        try:
            await asyncio.sleep(3600)  # Cada hora
            current_time = datetime.now().timestamp()

            old_reports = []
            for key, timestamp in hsm_sent_reports.items():
                if current_time - timestamp > 3600:  # 1 hora
                    old_reports.append(key)

            for key in old_reports:
                del hsm_sent_reports[key]

            logger.debug(f"🧹 [HSM CLEANUP] Eliminados {len(old_reports)} reportes HSM antiguos")

        except Exception as e:
            logger.error(f"Error en cleanup HSM: {str(e)}")

async def cleanup_inactivity_cooldowns():
    """Limpia cooldowns de inactividad expirados cada 10 minutos"""
    while True:
        try:
            await asyncio.sleep(600)  # Cada 10 minutos
            current_time = datetime.now().timestamp()

            expired_numbers = []
            for number, expiry_time in closed_by_inactivity.items():
                if current_time > expiry_time:
                    expired_numbers.append(number)

            for number in expired_numbers:
                del closed_by_inactivity[number]

            if expired_numbers:
                logger.debug(f"🧹 [COOLDOWN CLEANUP] Eliminados {len(expired_numbers)} cooldowns expirados")

        except Exception as e:
            logger.error(f"Error en cleanup cooldowns: {str(e)}")

# 🆕 AGREGAR AQUÍ (después de cleanup_old_evaluated_reports):
def log_evaluation_status():
    """Debug function para ver estado de evaluaciones"""
    logger.critical(f"📊 [EVAL STATUS] Reportes evaluados: {len(evaluated_reports)}")
    logger.critical(f"📊 [EVAL STATUS] HSM enviados: {len(hsm_sent_reports)}")
    logger.critical(f"📊 [EVAL STATUS] Sesiones activas: {len(user_sessions)}")
    
    for number, session in user_sessions.items():
        if hasattr(session, 'evaluation_state') and session.evaluation_state:
            logger.critical(f"📊 [EVAL STATUS] {number}: {session.evaluation_state} - {getattr(session, 'evaluation_folio', 'No folio')}")

# Add this at the module level
recently_completed_reports = {}  # key: phone_number, value: {timestamp, message_count}

# This function should be called when a report is successfully created
def mark_report_as_completed(phone_number):
    """
    Mark a phone number as having recently completed a report.
    This helps prevent normal thank you/farewell messages from triggering
    another report finalization cycle.
    
    Args:
        phone_number (str): User's phone number
    """
    logger.info(f"MARCANDO NÚMERO {phone_number} COMO COMPLETADO RECIENTEMENTE")  # Log explícito

    recently_completed_reports[phone_number] = {
        'timestamp': datetime.now().timestamp(),
        'message_count': 0  # Count of messages sent after completion
    }
    
    # Schedule cleanup after 3 minutes
    asyncio.create_task(remove_from_recently_completed(phone_number, 180))

# Helper function to remove from the tracking dict after a timeout
async def remove_from_recently_completed(phone_number, delay_seconds):
    """Remove a number from recently_completed_reports after a delay."""
    try:
        await asyncio.sleep(delay_seconds)
        if phone_number in recently_completed_reports:
            del recently_completed_reports[phone_number]
            logger.debug(f"Removed {phone_number} from recently completed reports tracking")
    except Exception as e:
        logger.error(f"Error removing {phone_number} from recently completed reports: {str(e)}")

# Modified is_finalization_message function
def is_finalization_message(text, from_number=None):
    """
    Determine if a message is attempting to finalize a report.
    This enhanced version detects many more ways to express "finalize a report" in Spanish.
    It also considers conversation context to avoid treating post-report thank you messages
    as new finalization requests.
    
    VERSIÓN CORREGIDA: Unifica diccionarios y extiende tiempo de protección
    
    Args:
        text (str): The message text to analyze
        from_number (str, optional): The phone number of the sender for context checking
        
    Returns:
        bool: True if the message should be treated as report finalization
    """
    if not text or not isinstance(text, str):
        return False
    
    # Convert to lowercase for case-insensitive matching
    text_lower = text.lower()
    
    # ✅ CORRECCIÓN: Verificar en AMBOS diccionarios (recently_completed_reports Y completed_reports)
    if from_number:
        current_time = datetime.now().timestamp()
        recently_completed = from_number in recently_completed_reports
        completed_recently = from_number in completed_reports
        
        # Verificar en CUALQUIERA de los dos diccionarios
        if recently_completed or completed_recently:
            elapsed_seconds = None
            message_count = 0
            
            # Obtener información de cualquier diccionario disponible
            if recently_completed:
                completion_info = recently_completed_reports[from_number]
                elapsed_seconds = current_time - completion_info['timestamp']
                message_count = completion_info.get('message_count', 0)
                
            elif completed_recently:
                completion_info = completed_reports[from_number]
                elapsed_seconds = current_time - completion_info['timestamp']
                message_count = 0  # completed_reports no tiene message_count
            
            # ✅ CORRECCIÓN: Extender tiempo de 60 a 180 segundos (3 minutos)
            if elapsed_seconds is not None and elapsed_seconds < 180:
                # ✅ CORRECCIÓN: Incrementar contador solo si recently_completed existe y es < 3
                if recently_completed and message_count < 3:
                    recently_completed_reports[from_number]['message_count'] += 1
                
                # Common thank you and farewell phrases in Spanish
                post_report_phrases = [
                    "gracias", "mil gracias", "muchas gracias", "excelente", "perfecto",
                    "genial", "que bueno", "qué bueno", "estupendo", "magnífico",
                    "es todo", "eso es todo", "eso era todo", "es todo por ahora",
                    "es todo lo que necesitada", "era todo", "no necesito nada más",
                    "así está bien", "así esta bien", "está bien", "esta bien", 
                    "ok", "okay", "bien", "bueno", "de acuerdo", "entendido"
                ]
                
                # If the message looks like a thank you after report completion
                if any(phrase in text_lower for phrase in post_report_phrases):
                    logger.critical(f"🚫 [POST-REPORT BLOCKED] '{text}' ignorado para {from_number} (hace {elapsed_seconds:.1f}s)")
                    return False
    
    # 1. Direct finalization keywords
    direct_keywords = [
        # Basic completion terms
        "listo", "lista", "ya terminé", "ya termine", "terminé", "termine", "he terminado", 
        "estoy listo", "estoy lista", "finalizar", "finaliza", "finalizado", "culminar",
        "completar", "completado", "completo", "completa", "acabar", "acabado", "acabé", 
        "acabe", "concluir", "concluido", "concluso", "concluyó", "concluyo",
        
        # Report specific
        "generar reporte", "genera reporte", "crear reporte", "crea reporte", "hacer reporte", 
        "haz reporte", "levantar reporte", "levanta reporte", "enviar reporte", "envía reporte",
        "reportar", "reporta", "reportarlo", "ingresar reporte", "ingresa reporte", "manda reporte",
        "mandar reporte", "envia", "enviar", "registrar", "registra", "registrarlo", "registro",
        
        # Send/submit variations
        "enviar", "envía", "mandar", "manda", "envíalo", "envialo", "mándalo", "mandalo",
        "someter", "somete", "somételo", "sometelo", "presentar", "presenta", "preséntalo",
        "presentarlo", "subir", "sube", "súbelo", "súbelo", "procesar", "procesa", "procésalo",
        
        # OK/Proceed variations
        "adelante", "procede", "proceda", "continua", "continúa", "avanza", "ejecuta", "ejecutar",
        "seguir adelante", "sigue adelante", "dale", "dale paso", "confirmar", "confirma", "aceptar",
        "acepta", "aprobar", "aprueba", "ok", "okay", "sí", "si", "afirmativo",
        
        # Añadir estas expresiones específicas
        "son todas", "es todo", "todas", "solo estas", "eso es todo", "ya están todas"
    ]
    
    # 2. Phrase patterns that indicate finalization
    finalization_phrases = [
        "ya está", "ya esta", "eso es todo", "es todo", "eso sería todo", "con eso", 
        "así está bien", "asi esta bien", "ya quedó", "ya quedo", "está completo", "esta completo",
        "puedes finalizar", "puedes terminar", "puedes proceder", "puedes continuar",
        "puedes procesar", "puedes enviarlo", "puedes mandarlo", "puedes registrarlo",
        "por favor finaliza", "por favor termina", "por favor procede", "por favor continúa",
        "favor de finalizar", "favor de terminar", "favor de proceder", "favor de continuar",
        "favor de enviarlo", "favor de mandarlo", "favor de registrarlo",
        "no más fotos", "no más imágenes", "no más", "solo esas fotos", "solo esas imágenes",
        "son todas las fotos", "son todas las imágenes", "ya tengo todas", "ya mandé todas",
        "ya envié todas", "puedes hacer", "puedes generar", "genera el reporte", "crea el reporte",
        "son todas", "es todo", "todas", "esas son todas"  # Repetimos aquí para asegurar detección
    ]
    
    # 3. Negative-word filters (words that might indicate the user is NOT ready)
    negative_indicators = [
        "no estoy listo", "no he terminado", "no está listo", "no esta listo", "todavía no", 
        "aún no", "falta", "faltan", "espera", "espere", "aguanta", "aguante", "detente", 
        "más tarde", "luego", "después", "despues", "no lo envíes", "no lo envies", 
        "no lo mandes", "no finalices", "no termines", "no generes", "no crees",
        "no quiero finalizar", "no quiero terminar", "no deseo finalizar", "no deseo terminar",
        "no lo hagas"
    ]

    # Verificación exacta para frases comunes muy cortas
    exact_phrases = ["son todas", "es todo", "listo", "todas", "solo estas"]
    if text_lower.strip() in exact_phrases:
        return True
    
    # Check for direct keywords (simple full or partial matches)
    if any(keyword in text_lower.split() or keyword in text_lower for keyword in direct_keywords):
        # But make sure none of the negative indicators are present
        if not any(neg in text_lower for neg in negative_indicators):
            return True
    
    # Check for phrase patterns (more complex expressions)
    if any(phrase in text_lower for phrase in finalization_phrases):
        # But make sure none of the negative indicators are present
        if not any(neg in text_lower for neg in negative_indicators):
            return True
    
    # Additional context-aware checks for very short responses
    if len(text_lower.split()) <= 3:  # Very short responses
        # Common short approvals
        short_approvals = ["ok", "sí", "si", "yes", "ya", "dale", "eso", "ese", "esta bien", "está bien", "listo"]
        if any(text_lower == word or text_lower.startswith(word + " ") or text_lower.endswith(" " + word) for word in short_approvals):
            return True
            
        # Check for standalone "1" or "ok" which users sometimes send as confirmation
        if text_lower in ["1", "ok", "👍", "👌"]:
            return True
    
    # If none of the above conditions match, it's not a finalization message
    return False

async def save_client_selection2_with_auto_marking(yoga_number: str, selection1: str, selection2: str, selection3: str,
                                                  selection4: str, selection5: str, selection6: str, selection7: str, 
                                                  selection8: str = None, images_list: list = None, descriptions_list: list = None):
    """
    🛡️ VERSIÓN PROTEGIDA: Usa el sistema anti-duplicación
    """
    try:
        # USAR LA FUNCIÓN PROTEGIDA
        folio = await save_client_selection2_protected(
            yoga_number, selection1, selection2, selection3,
            selection4, selection5, selection6, selection7,
            selection8, images_list, descriptions_list
        )
        
        # Si fue exitoso, hacer auto-marking
        if folio and "Folio:" in folio and folio != "Folio: Generado":
            logger.critical(f"✅ [AUTO-MARKING] Marcando {yoga_number} como completado con {folio}")
            
            # El dedup_manager ya maneja la protección post-reporte
            # Solo necesitamos mantener recently_completed_reports para compatibilidad
            recently_completed_reports[yoga_number] = {
                'timestamp': datetime.now().timestamp(),
                'message_count': 0
            }
            # 🆕 AGREGAR LIMPIEZA INMEDIATA (ESTO FALTABA)
            logger.critical(f"🧹 [IMMEDIATE CLEANUP] Programando limpieza inmediata para {yoga_number}")
            asyncio.create_task(complete_cleanup_after_report(yoga_number, 1))  # 1 segundo
        
        return folio
        
    except Exception as e:
        logger.error(f"❌ Error en save_client_selection2_with_auto_marking: {str(e)}")
        raise

async def should_block_gratitude_message(text, from_number):
    """
    Verificación ADICIONAL para bloquear mensajes de gratitud
    """
    if not text or not from_number:
        return False
    
    text_lower = text.lower().strip()
    
    # Verificar en AMBOS diccionarios
    in_recently = from_number in recently_completed_reports
    in_completed = from_number in completed_reports
    
    if not (in_recently or in_completed):
        return False
    
    current_time = datetime.now().timestamp()
    
    # Obtener timestamp de cualquier diccionario
    if in_recently:
        elapsed = current_time - recently_completed_reports[from_number]['timestamp']
    elif in_completed:
        elapsed = current_time - completed_reports[from_number]['timestamp']
    
    # Si fue hace menos de 3 minutos
    if elapsed < 180:
        gratitude_words = [
            "gracias", "excelente", "perfecto", "genial", "ok", "bueno", 
            "está bien", "de acuerdo", "mil gracias", "muchas gracias"
        ]
        
        # Si es SOLO una palabra de gratitud (mensaje corto)
        if any(word == text_lower or text_lower.startswith(word) for word in gratitude_words):
            logger.critical(f"🚫 [GRATITUDE BLOCKED] '{text}' bloqueado para {from_number} (hace {elapsed:.1f}s)")
            return True
    
    return False

async def remove_from_completed_reports(number, delay_seconds):
    """Remove a number from completed_reports after a delay with error handling."""
    try:
        await asyncio.sleep(delay_seconds)
        if number in completed_reports:
            del completed_reports[number]
            logger.debug(f"Removed {number} from completed reports after {delay_seconds} seconds")
    except Exception as e:
        logger.error(f"Error removing {number} from completed reports: {str(e)}")

async def send_chat2desk_message(phone_number, client_id, channel_id, text, transport="wa_direct"):
    """Send a message via Chat2Desk API. Supports both wa_direct (WhatsApp) and widget (web chat)."""
    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"

        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }

        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(chat2desk_url, json=data, headers=headers)
            
        if response.status_code == 200:
            logger.debug(f"Message sent successfully to Chat2Desk")
            return True
        else:
            logger.error(f"Error sending message to Chat2Desk: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Exception while sending Chat2Desk message: {str(e)}")
        return False

# Modificar la función process_and_save_report para que también haga limpieza completa
async def process_and_save_report_with_cleanup(from_number, location, images=None, descriptions=None):
    """
    Versión mejorada que incluye limpieza completa después de crear reporte exitoso.
    """
    # Ejecutar la función original
    result = await process_and_save_report(from_number, location, images, descriptions)
    
    # Si fue exitoso, hacer limpieza completa
    if result['status'] == 'success':
        logger.critical(f"🧹 [MANUAL SUCCESS] Programando limpieza completa para {from_number}")
        asyncio.create_task(complete_cleanup_after_report(from_number, 10))
    
    return result

def should_ignore_message(message_text, message_type, from_number=None):
    """
    Determina si un mensaje debe ser ignorado (echo del bot, etc.)
    """
    # 1. Ignorar mensajes salientes
    if message_type == 'to_client':
        return True, "Mensaje saliente ignorado"
    
    # 2. Ignorar mensajes que no son del cliente
    if message_type != 'from_client':
        return True, f"Mensaje tipo {message_type} ignorado"
    
    # 3. Ignorar echos de notificaciones de timeout
    if is_timeout_notification_echo(message_text):
        logger.critical(f"🚫 [ECHO DETECTED] Ignorando echo de timeout para {from_number}: '{message_text[:50]}...'")
        return True, "Echo de timeout ignorado"
    
    # 4. Verificar si viene de un número que acaba de crear reporte
    if (from_number and from_number in completed_reports and 
        message_text and len(message_text.strip()) > 10):
        
        recent_report = completed_reports[from_number]
        elapsed_seconds = datetime.now().timestamp() - recent_report['timestamp']
        
        # Si el reporte fue creado en los últimos 30 segundos
        if elapsed_seconds < 30:
            logger.critical(f"🚫 [POST-REPORT] Ignorando mensaje post-reporte para {from_number} (hace {elapsed_seconds:.1f}s): '{message_text[:30]}...'")
            return True, "Mensaje post-reporte ignorado"
    
    return False, "Mensaje válido para procesar"

def is_timeout_notification_echo(message_text):
    """
    Detecta si un mensaje es un echo de nuestra notificación de timeout.
    """
    timeout_indicators = [
        "🚀 ¡tu reporte ya está listo!",
        "✅ folio:",
        "debido a la inactividad",
        "hemos generado tu folio automáticamente",
        "para que puedas continuar reportando"
    ]
    
    if not message_text:
        return False
    
    text_lower = message_text.lower()
    return any(indicator in text_lower for indicator in timeout_indicators)

# Modify the process_and_save_report function
async def process_and_save_report(from_number, location, images=None, descriptions=None):
    """
    Process and save a report with improved error handling and deduplication.
    Returns a dict with status and additional information.
    
    Args:
        from_number (str): Sender's phone number
        location (str): Location information  
        images (list): List of image URLs
        descriptions (list): List of image descriptions
    """
    logger.debug(f"process_and_save_report: Processing report for {from_number}")
    log_operational_decision_trace(
        from_number,
        "process_and_save_report_start",
        location=location,
        images_count=len(images or []),
        descriptions_count=len(descriptions or []),
    )
    
    # Initialize with empty lists if None
    images = images or []
    descriptions = descriptions or []
    
    # Log received images for debugging
    logger.debug(f"Received {len(images)} images for processing")
    for i, img in enumerate(images):
        logger.debug(f"  Image {i+1}: {img[:50]}...")
    
    # Check for recent report (deduplication)
    recent_report = has_recent_report(from_number)
    if recent_report:
        logger.warning(f"Recent report found for {from_number}, folio: {recent_report['folio']}")
        return {
            'status': 'duplicate',
            'message': f"Tu reporte ya fue creado recientemente (folio: {recent_report['folio']})",
            'folio': recent_report['folio']
        }
    
    # Check for empty images
    if not images:
        return {
            'status': 'no_images',
            'message': "No se han adjuntado imágenes al reporte. Por favor, envía al menos una imagen."
        }
    
    # Mark as in progress (with thread safety)
    with reports_lock:
        if from_number in reports_in_progress and reports_in_progress[from_number]:
            return {
                'status': 'in_progress',
                'message': "Tu reporte ya está siendo procesado. Por favor, espera unos momentos."
            }
        reports_in_progress[from_number] = True
    
    try:
        # Parse location into components
        street = "No especificada"
        neighborhood = "No especificada"
        street_number = "0000"  # Default value
        
        if location:
            location_parts = location.split(',')
            if len(location_parts) >= 2:
                street = location_parts[0].strip()
                neighborhood = location_parts[1].strip()
            else:
                street = location

        selections = {
            "selection1": get_user_answer(from_number, "selection1"),
            "selection2": get_user_answer(from_number, "selection2"),
            "selection3": "",  # siempre vacío
            "selection4": get_user_answer(from_number, "selection4"),
            "selection5": get_user_answer(from_number, "selection5"),
            "selection6": get_user_answer(from_number, "selection6"),
            "selection7": get_user_answer(from_number, "selection7"),
        }

        log_operational_decision_trace(
            from_number,
            "process_and_save_report_payload",
            selections=selections,
            report_state=build_report_state_snapshot(from_number),
        )

        logger.critical(f"PASANDO {len(images)} IMÁGENES A save_client_selection2_protected")
        for i, img in enumerate(images):
            logger.critical(f"  Imagen {i+1}: {img[:50]}...")

        # Create the report
        folio = await save_client_selection2_protected(
            yoga_number=from_number,
            images_list=images,
            descriptions_list=descriptions,
            **selections
        )

        current_time = datetime.now().timestamp()
        log_operational_decision_trace(
            from_number,
            "process_and_save_report_result",
            raw_result=folio,
            current_time=current_time,
        )

        if isinstance(folio, str) and folio.startswith("Folio:"):
            logger.info(f"Report successfully created for {from_number}, folio: {folio}")
            return {
                'status': 'success',
                'message': f"Reporte creado exitosamente. Folio: {folio}",
                'folio': folio
            }

        if isinstance(folio, str) and folio.startswith("VALIDATION_BLOCK:"):
            logger.warning(f"Report validation blocked for {from_number}: {folio}")
            return {
                'status': 'validation_block',
                'message': folio.replace("VALIDATION_BLOCK:", "", 1).strip() or folio,
                'raw_result': folio
            }

        if isinstance(folio, str) and folio.startswith("Error:"):
            logger.error(f"Report creation returned error for {from_number}: {folio}")
            return {
                'status': 'error',
                'message': folio
            }

        logger.error(f"Unexpected report creation result for {from_number}: {folio}")
        return {
            'status': 'error',
            'message': f"Resultado inesperado al crear el reporte: {folio}"
        }
        
    except Exception as e:
        logger.error(f"Error processing report for {from_number}: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error al procesar el reporte: {str(e)}"
        }
    finally:
        # Always release the "in progress" state
        with reports_lock:
            if from_number in reports_in_progress:
                reports_in_progress[from_number] = False

# Helper function to remove a number from the finalized set after a delay
async def remove_from_finalized(number, delay_seconds):
    await asyncio.sleep(delay_seconds)
    if number in finalized_report_numbers:
        finalized_report_numbers.remove(number)
        logger.debug(f"Número {number} removido de la lista de reportes finalizados después de {delay_seconds} segundos")

async def remove_from_transferred(number, delay_seconds):
    await asyncio.sleep(delay_seconds)
    if number in transferred_numbers:
        transferred_numbers.remove(number)
        logger.debug(f"Bot re-enabled for {number} after {delay_seconds} seconds")
# ------------------------------
# Función de ciclo de vida (lifespan)
# ------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 INICIANDO SERVIDOR - Creando tareas de background...")
    logger.critical("🚀 INICIANDO SERVIDOR - Creando tareas de background...")
    # Startup: se lanzan las tareas de verificación
    asyncio.create_task(check_inactivity())
    asyncio.create_task(check_report_timeouts())
    asyncio.create_task(monitor_reply_detection())
    
    # 🆕 NUEVA TAREA: Limpieza del gestor anti-duplicación
    asyncio.create_task(dedup_cleanup_task(dedup_manager))
    logger.critical("🛡️ [DEDUP] Tarea de limpieza anti-duplicación iniciada")

    # 🆕 AGREGAR ESTA LÍNEA:
    asyncio.create_task(cleanup_hsm_reports())

    # 🆕 NUEVA TAREA: Limpieza de cooldowns de inactividad
    asyncio.create_task(cleanup_inactivity_cooldowns())
    logger.critical("🧹 [COOLDOWN] Tarea de limpieza de cooldowns de inactividad iniciada")

    yield
    # Shutdown: se puede agregar lógica de limpieza si se requiere
    print("🛑 CERRANDO SERVIDOR...")
    # Shutdown: se puede agregar lógica de limpieza si se requiere
app = FastAPI(lifespan=lifespan)

router = APIRouter()


# Add this at the module level (outside of the function)
# Initialize the TTL cache - messages expire after 1 hour, max 1000 entries
processed_message_ids = TTLCache(max_size=1000, ttl_seconds=3600)
recent_direct_message_keys = TTLCache(max_size=2000, ttl_seconds=20)
recent_outbound_response_keys = TTLCache(max_size=3000, ttl_seconds=90)
widget_guard_lock = threading.RLock()
widget_identity_events = OrderedDict()
widget_fingerprint_events = OrderedDict()
widget_text_events = OrderedDict()

WIDGET_IDENTITY_WINDOW_SECONDS = 30
WIDGET_IDENTITY_LIMIT = 5
WIDGET_FINGERPRINT_WINDOW_SECONDS = 60
WIDGET_FINGERPRINT_LIMIT = 8
WIDGET_TEXT_WINDOW_SECONDS = 120
WIDGET_TEXT_LIMIT = 3


def _cleanup_widget_guard_cache(cache, window_seconds):
    now = datetime.now()
    expired_keys = [
        key for key, timestamps in cache.items()
        if not timestamps or now - timestamps[-1] > timedelta(seconds=window_seconds)
    ]
    for key in expired_keys:
        del cache[key]


def _register_widget_guard_event(cache, key, window_seconds):
    now = datetime.now()
    timestamps = cache.setdefault(key, [])
    cutoff = now - timedelta(seconds=window_seconds)
    timestamps[:] = [ts for ts in timestamps if ts > cutoff]
    timestamps.append(now)
    return len(timestamps)


def normalize_widget_text(text):
    if not text:
        return ""
    normalized = " ".join(str(text).strip().lower().split())
    return normalized[:500]


def evaluate_widget_abuse(payload):
    """
    Evalúa patrones de abuso específicos del widget sin depender de la IP real.
    """
    transport = payload.get("transport", "wa_direct")
    if transport != "widget":
        return False, {}

    client_id = str(payload.get("client_id") or "")
    dialog_id = str(payload.get("dialog_id") or "")
    client = payload.get("client") or {}
    chat_phone = str(client.get("phone") or "")
    request_id = str(payload.get("request_id") or "")
    message_id = str(payload.get("message_id") or "")
    raw_text = payload.get("text") or ""
    normalized_text = normalize_widget_text(raw_text)
    is_new_client = bool(payload.get("is_new_client"))
    is_new_request = bool(payload.get("is_new_request"))

    identity_key = f"{client_id}:{dialog_id}:{chat_phone}"
    fingerprint_key = chat_phone or f"{client_id}:{dialog_id}"
    text_key = normalized_text

    with widget_guard_lock:
        _cleanup_widget_guard_cache(widget_identity_events, WIDGET_IDENTITY_WINDOW_SECONDS)
        _cleanup_widget_guard_cache(widget_fingerprint_events, WIDGET_FINGERPRINT_WINDOW_SECONDS)
        _cleanup_widget_guard_cache(widget_text_events, WIDGET_TEXT_WINDOW_SECONDS)

        identity_hits = _register_widget_guard_event(
            widget_identity_events, identity_key, WIDGET_IDENTITY_WINDOW_SECONDS
        )
        fingerprint_hits = _register_widget_guard_event(
            widget_fingerprint_events, fingerprint_key, WIDGET_FINGERPRINT_WINDOW_SECONDS
        )
        text_hits = 0
        if text_key:
            text_hits = _register_widget_guard_event(
                widget_text_events, text_key, WIDGET_TEXT_WINDOW_SECONDS
            )

    if identity_hits > WIDGET_IDENTITY_LIMIT:
        return True, {
            "reason": "identity_rate_limit",
            "identity_hits": identity_hits,
            "fingerprint_hits": fingerprint_hits,
            "text_hits": text_hits,
            "client_id": client_id,
            "dialog_id": dialog_id,
            "chat_phone": chat_phone,
            "request_id": request_id,
            "message_id": message_id,
        }

    if is_new_client and is_new_request and fingerprint_hits > WIDGET_FINGERPRINT_LIMIT:
        return True, {
            "reason": "new_widget_fingerprint_burst",
            "identity_hits": identity_hits,
            "fingerprint_hits": fingerprint_hits,
            "text_hits": text_hits,
            "client_id": client_id,
            "dialog_id": dialog_id,
            "chat_phone": chat_phone,
            "request_id": request_id,
            "message_id": message_id,
        }

    if text_key and text_hits >= WIDGET_TEXT_LIMIT:
        return True, {
            "reason": "repeated_widget_text",
            "identity_hits": identity_hits,
            "fingerprint_hits": fingerprint_hits,
            "text_hits": text_hits,
            "client_id": client_id,
            "dialog_id": dialog_id,
            "chat_phone": chat_phone,
            "request_id": request_id,
            "message_id": message_id,
            "text_sample": normalized_text[:120],
        }

    return False, {
        "identity_hits": identity_hits,
        "fingerprint_hits": fingerprint_hits,
        "text_hits": text_hits,
    }


def log_widget_request_metadata(request):
    forwarded_for = request.headers.get("x-forwarded-for")
    real_ip = request.headers.get("x-real-ip")
    cf_connecting_ip = request.headers.get("cf-connecting-ip")
    user_agent = request.headers.get("user-agent")
    referer = request.headers.get("referer")
    remote_host = request.client.host if request.client else None

    logger.info(
        "[WIDGET META] remote_host=%s cf_connecting_ip=%s x_real_ip=%s x_forwarded_for=%s referer=%s user_agent=%s",
        remote_host,
        cf_connecting_ip,
        real_ip,
        forwarded_for,
        referer,
        user_agent,
    )

#Add this function to identify and filter out bot-originated messages
def is_bot_generated_message(message_text, recent_ai_messages=None):
    """
    Versión mejorada que maneja mensajes citados y no los confunde con ecos del bot.
    
    Args:
        message_text (str): El mensaje a analizar
        recent_ai_messages (list): Mensajes recientes del AI
        
    Returns:
        bool: True si es un mensaje del bot, False si es del usuario
    """
    if not message_text:
        return False

    # NUEVO: Primero verificar si es un mensaje citado
    quoted_info = extract_quoted_message_content(message_text)
    
    if quoted_info['is_quoted']:
        logger.critical(f"🔤 [QUOTED DETECTED] Texto citado: '{quoted_info['quoted_text'][:30]}...', Respuesta usuario: '{quoted_info['user_response']}'")
        # Si es un mensaje citado, NO es un echo del bot - es una respuesta legítima del usuario
        return False
    
    # Continuar con la lógica original para mensajes no citados
    exact_bot_patterns = [
        "he recibido tu imagen",
        "he recibido otra imagen", 
        "tienes * en total",
        "puedes enviar más imágenes",
        "puedes seguir enviando imágenes",
        "[image_received]",
        "ubicación registrada",
        "para finalizar tu reporte"
    ]

    # Use glob-style pattern matching (with * as wildcard)
    for pattern in exact_bot_patterns:
        if pattern.lower() in message_text.lower():
            return True
    
    # Check if the message closely matches a recent AI message
    if recent_ai_messages:
        for ai_message in recent_ai_messages:
            # If message is very similar to a recent AI message, it's likely an echo
            if ai_message == message_text or (
                len(ai_message) > 20 and len(message_text) > 20 and
                (ai_message in message_text or message_text in ai_message)
            ):
                return True
    
    return False

def get_images_from_payload(payload):
    global user_sessions, report_sessions
    """
    Extrae URLs de imágenes del payload de Chat2Desk.
    
    Args:
        payload (dict): El payload recibido de Chat2Desk
        
    Returns:
        list: Lista de URLs de imágenes válidas
    """
    fotos_urls = []
    from_number = payload.get('client', {}).get('phone')
    # Extraer foto si existe en el payload
    
    if payload.get("photo") and from_number:
        photo_url = payload.get("photo")
        # Verificar si debería ser una nueva sesión
        if from_number not in user_sessions and from_number in report_sessions:
            # Si hay user_sessions pero no report_sessions, limpiar report_sessions
            logger.info(f"Detectada posible sesión huérfana para {from_number}, limpiando datos de reporte antiguos")
            del report_sessions[from_number]
        
        if photo_url and isinstance(photo_url, str) and (photo_url.startswith('http') or 'storage.chat2desk.com' in photo_url):
            fotos_urls.append(photo_url)
            logger.debug(f"Foto capturada del payload: {photo_url}")
    
    # También podemos buscar fotos en otros campos si es necesario
    # Por ejemplo, si hubiera un campo "attachments" o similar
    
    return fotos_urls


@router.post("/whatsapp")
async def whatsapp(request: Request):
    logger.debug("Iniciando procesamiento del mensaje de WhatsApp.")
    # Configuración de base de datos y demás servicios
    db = LocalStorage()
    args = request.query_params
    config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
    whatsapp_functions = [
        save_client_selection2_guarded if func.__name__ == "save_client_selection2"
        else transfer_to_group_guarded if func.__name__ == "transfer_to_group"
        else func
        for func in registered_functions
    ]
    function_manager = FunctionManager(whatsapp_functions)
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=OPENAI_HTTP_TIMEOUT,
        max_retries=OPENAI_MAX_RETRIES,
    )

    # Check if this is a message from a human agent with the human takeover message
    BOT_OPERATOR_IDS = {228522, 228524}
    
    
    try:
        payload = await request.json()  # Recibimos el payload como JSON
        print(f"Payload recibido: {payload}")
        #reply_context = extract_reply_context(payload)

        # IMPORTANTE: Verificar si es un mensaje de un cliente o una respuesta del sistema
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        message_type = payload.get('type', '')
        uid = payload.get('message_id', '')
        message_text = payload.get('text', '')
        channel_id = payload.get('channel_id')
        client_id = payload.get('client_id')
        hook_type = payload.get('hook_type', '')
        operator_id = payload.get('operator_id', '')
        message_id = payload.get('message_id')
        transport = payload.get('transport', 'wa_direct')  # Extract transport: wa_direct or widget
        request_id = payload.get('request_id')

        if transport == 'widget':
            log_widget_request_metadata(request)
            should_block, widget_guard_metadata = evaluate_widget_abuse(payload)
            if should_block:
                logger.warning(
                    f"🛡️ [WIDGET GUARD] Bloqueando mensaje sospechoso: {json.dumps(widget_guard_metadata, ensure_ascii=False)}"
                )
                return JSONResponse(content={"status": True, "message": "Mensaje de widget bloqueado"})

        if reconcile_outgoing_campaign_system_event(db, payload):
            return JSONResponse(content={"status": True, "message": "Estado de campaña actualizado desde evento system"})
        if reconcile_outgoing_campaign_outbox_event(db, payload):
            return JSONResponse(content={"status": True, "message": "Webhook de campaña saliente conciliado"})

        if message_type == 'from_client' and from_number:
            record_outgoing_campaign_reply(db, from_number, body or message_text or "")

        # 🆕 VERIFICAR SI ES EL NÚMERO ESPECIAL
        # ========EQUIPO CIAC============
        if from_number == SPECIAL_NUMBER:
            logger.critical(f"🚨 NÚMERO ESPECIAL DETECTADO ({SPECIAL_NUMBER}) - ENVIANDO A WEBHOOK")
            
            webhook_url = "https://n8n.evolutek.info/webhook/fd814da2-b597-40f6-9f64-e812c8551207"
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        webhook_url,
                        json=payload,
                        timeout=30.0
                    )
                    
                if response.status_code == 200:
                    logger.critical(f"✅ Webhook respondió correctamente para {SPECIAL_NUMBER}")
                    return JSONResponse(content={
                        "status": True,
                        "message": "Mensaje de número especial enviado al webhook"
                    })
                else:
                    logger.error(f"❌ Error en webhook para {SPECIAL_NUMBER}: {response.status_code}")
                    return JSONResponse(content={
                        "status": False,
                        "error": f"Webhook respondió con código {response.status_code}"
                    }, status_code=500)
                    
            except Exception as e:
                logger.error(f"💥 Error al enviar a webhook: {str(e)}")
                return JSONResponse(content={
                    "status": False,
                    "error": f"Error al enviar a webhook: {str(e)}"
                }, status_code=500)
            # ========EQUIPO CIAC============
            
        if message_type == 'to_client' and message_text:
            logger.critical(f"🔍 [FILTER DEBUG] Evaluando mensaje: '{message_text}'")
            # 🚫 FILTRO ULTRA ROBUSTO - Bloquear CUALQUIER mensaje de evaluación
            message_lower = message_text.lower()
            
            # Si contiene CUALQUIERA de estas palabras, bloquear
            evaluation_indicators = [
                "evaluación", "evaluacion", 
                "sí o no", "si o no",
                "*sí* o *no*", "*si* o *no*",
                "está de acuerdo", "esta de acuerdo",
                "responde", "responda",
                "continuar con", "del 1 al 5"
            ]
            
            if any(indicator in message_lower for indicator in evaluation_indicators):
                logger.debug(f"🚫 [EVALUATION BLOCK] Bloqueando: {message_text[:50]}...")
                return JSONResponse(content={"status": True, "message": "Mensaje de evaluación bloqueado"})
        
        hsm_result = await handle_hsm_conclusion_notification(payload, from_number)
        if hsm_result:
            return JSONResponse(content=hsm_result)

        current_time = datetime.now().timestamp()
        
        # Handle None values in body
        if body is None:
            body = ""
            logger.debug("Message with None body detected, setting to empty string")
        
        # LOG EXPLÍCITO para verificar mensajes con el texto detonante
        if is_bot_return_message(message_text):
            logger.critical(f"MENSAJE CON TEXTO DETONANTE DETECTADO - Type: {message_type}, Operator: {operator_id}, Text: {message_text[:50]}")

        # 🎯 PRIMERO: Verificar mensajes de takeover ANTES de filtrar
        if message_type == 'to_client' and is_human_takeover_message(message_text):
            logger.info(f"Human agent takeover detected for {from_number}")
            
            expiration_time = datetime.now().timestamp() + (30 * 60)
            transferred_numbers[from_number] = expiration_time
            
            try:
                system_notification = Message(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    senderName="System",
                    message=f"[SYSTEM] Conversation transferred to human agent until {datetime.fromtimestamp(expiration_time).strftime('%H:%M:%S')}",
                    number=from_number,
                    uid=f"takeover-{datetime.now().timestamp()}",
                    direction="system",
                    mtype="text",
                    source="whatsapp"
                )
                db.Insert(system_notification)
            except Exception as e:
                logger.error(f"Error recording human takeover: {str(e)}")
            
            return JSONResponse(content={"status": True, "message": "Human agent takeover registered"})

        # 🎯 SEGUNDO: Verificar return to AI
        if message_type == 'to_client' and is_bot_return_message(message_text):
            logger.info(f"!!! HUMAN AGENT GOODBYE DETECTED !!! Releasing control to AI for next inbound message on {from_number}")
            
            if from_number in transferred_numbers:
                del transferred_numbers[from_number]
                logger.debug(f"Removed {from_number} from transferred_numbers dictionary")
                
            return_timestamp = parse_chat2desk_event_timestamp(payload.get("event_time")) or datetime.now().timestamp()
            recently_returned_to_bot[from_number] = return_timestamp
            bot_returned_at[from_number] = return_timestamp
            logger.info(f"Added {from_number} to recently_returned_to_bot with grace period of {BOT_GRACE_PERIOD} seconds")
            
            asyncio.create_task(remove_from_recently_returned(from_number, BOT_GRACE_PERIOD))
            log_operational_decision_trace(
                from_number,
                "human_goodbye_release",
                operator_id=operator_id,
                message_preview=message_text[:240],
                action="release_control_without_autogreeting",
                return_timestamp=return_timestamp,
            )
            return JSONResponse(content={"status": True, "message": "Control released to AI for next inbound message"})

        # 🎯 TERCERO: Detección automática por operator_id
        human_operator_active = (
            message_type == 'to_client' and
            hook_type == 'outbox' and
            is_non_bot_operator(payload.get('operator_id'), BOT_OPERATOR_IDS) and
            from_number not in recently_returned_to_bot
        )

        if human_operator_active:
            expiration_time = datetime.now().timestamp() + (30 * 60)
            transferred_numbers[from_number] = expiration_time

        if human_operator_active:
            
            logger.info(f"Detección automática: Agente humano (ID {payload.get('operator_id')}) tomó la conversación con {from_number}")

            try:
                system_notification = Message(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    senderName="System",
                    message=f"[SYSTEM] Detección automática: Conversación transferida a agente humano hasta {datetime.fromtimestamp(expiration_time).strftime('%H:%M:%S')}",
                    number=from_number,
                    uid=f"auto-takeover-{datetime.now().timestamp()}",
                    direction="system",
                    mtype="text",
                    source="whatsapp"
                )
                db.Insert(system_notification)
            except Exception as e:
                logger.error(f"Error registrando transferencia automática: {str(e)}")
        elif (
            message_type == 'to_client' and
            hook_type == 'outbox' and
            is_non_bot_operator(payload.get('operator_id'), BOT_OPERATOR_IDS) and
            from_number in recently_returned_to_bot
        ):

            grace_time = int(BOT_GRACE_PERIOD - (datetime.now().timestamp() - recently_returned_to_bot[from_number]))
            logger.info(f"Ignorando detección automática para {from_number} - en período de gracia ({grace_time} segundos restantes)")

        # 🎯 CUARTO: Verificar si ya está transferido
        if from_number in transferred_numbers and current_time < transferred_numbers[from_number]:
            logger.info(f"Ignoring message from {from_number} as it's being handled by a human agent (expires in {int(transferred_numbers[from_number] - current_time)} seconds)")
            return JSONResponse(content={"status": True, "message": "Message ignored - conversation transferred to human agent"})
        elif from_number in transferred_numbers:
            logger.info(f"Transfer for {from_number} has expired, bot is now responding again")
            del transferred_numbers[from_number]

        proactive_guard = None
        if message_type == 'from_client' and from_number:
            proactive_guard = get_active_proactive_campaign_guard(db, from_number)
            if proactive_guard:
                logger.critical(
                    "🛑 [PROACTIVE HSM GUARD] phone=%s campaign_id=%s campaign_name=%s campaign_kind=%s body=%s",
                    proactive_guard["phone"],
                    proactive_guard["campaign_id"],
                    proactive_guard["campaign_name"],
                    proactive_guard["campaign_kind"],
                    _truncate_for_log(body or message_text, 180),
                )
                return JSONResponse(
                    content={
                        "status": True,
                        "message": "Message ignored - proactive campaign guard active",
                        "campaign_id": proactive_guard["campaign_id"],
                        "campaign_kind": proactive_guard["campaign_kind"],
                    }
                )

        # 🎯 QUINTO: Aplicar filtros generales (DESPUÉS de detecciones de takeover)
        should_ignore, ignore_reason = should_ignore_message(body, message_type, from_number)
        if should_ignore:
            logger.debug(f"🚫 [FILTER] {ignore_reason} para {from_number}")
            return JSONResponse(content={"status": True, "message": ignore_reason})
        
        # Ahora procesar las imágenes cuando ya tenemos from_number
        fotos_urls = get_images_from_payload(payload)

        # Si hay un reporte en progreso, añadir las imágenes a su lista
        if from_number in report_sessions and fotos_urls:
            for foto_url in fotos_urls:
                if foto_url not in report_sessions[from_number]["images"]:
                    report_sessions[from_number]["images"].append(foto_url)
                    report_sessions[from_number]["image_descriptions"].append("Imagen adicional")
                    report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                    logger.info(f"Imagen añadida al reporte en progreso para {from_number}")

        # fotos_urls = []
        # # Si hay una foto en este mensaje, guardarla
        # if payload.get("photo"):
        #     photo_url = payload.get("photo")
        #     if photo_url and isinstance(photo_url, str) and (photo_url.startswith('http') or 'storage.chat2desk.com' in photo_url):
        #         fotos_urls.append(photo_url)
        #         logger.debug(f"Foto capturada del payload: {photo_url}")

        # Log ALL autoreply messages with full details
        if message_type == 'autoreply':
            # Create a proper debug log with all relevant fields
            
            # Obtener el texto y normalizarlo (eliminar espacios extras, convertir a minúsculas)
            raw_text = payload.get('text', '')
            if raw_text:
                # Imprimir el texto exacto para depuración
                print(f"Texto original: {repr(raw_text)}")
                # Normalizar el texto para hacer comparaciones más robustas
                # - Convertir a minúsculas
                # - Eliminar saltos de línea y caracteres especiales
                # - Eliminar espacios extras
                normalized_text = raw_text.lower().replace('\n', ' ').replace('-', '').strip()
                print(f"Texto normalizado: {repr(normalized_text)}")

                # Buscar patrones clave en lugar de coincidencias exactas
                if 'scenario' in normalized_text and 'title' in normalized_text and 'default' in normalized_text:
                    # Es probablemente un mensaje de escenario
                    if 'end' in normalized_text and 'finalizar' in normalized_text:
                        # Es un mensaje de finalización
                        logger.debug(f"Bloqueando mensaje de finalización de escenario: {uid}")
                        return JSONResponse(content={"status": True, "message": "Mensaje de escenario de finalización bloqueado"})
            
            debug_info = {
                "message_id": uid,
                "type": message_type,
                "hook_type": hook_type,
                "text_length": len(message_text) if message_text else 0,
                "text_sample": message_text[:50] if message_text else "None",
                "text_contains_scenario": 'scenario.scenarioTitle.default' in (message_text or ""),
                "text_contains_finalizar": 'End - Finalizar este chat' in (message_text or ""),
                "raw_text": repr(message_text),  # This shows exact string with escape codes
            }
            logger.debug(f"AUTOREPLY DEBUG: {json.dumps(debug_info)}")
            
            # Now with explicit detailed checks, try to catch these messages
            if message_text and 'scenario' in message_text and 'default' in message_text and 'End' in message_text:
                logger.info(f"BLOCKING SCENARIO MESSAGE: {repr(message_text)}")
                return JSONResponse(content={"status": True, "message": "Mensaje de escenario bloqueado con debug"})

        # Then continue with your existing filter logic:
        if (message_type == 'autoreply' and 
            'scenario.scenarioTitle.default' in (message_text or "") and 
            'End - Finalizar este chat' in (message_text or "")):
            
            logger.debug(f"Bloqueando mensaje autoreply de escenario de finalización: {uid}")
            return JSONResponse(content={"status": True, "message": "Mensaje de escenario de fin ignorado"})
        
        # Solo procesar mensajes que vienen del cliente (ignorar webhooks de mensajes enviados por el bot)
        if message_type == 'to_client':
            logger.debug(f"Ignorando mensaje saliente con type={message_type}")
            return JSONResponse(content={"status": True, "message": "Mensaje saliente ignorado"})
            
        # Only process incoming client messages
        if message_type != 'from_client':
            logger.debug(f"Ignorando mensaje con type={message_type} que no es from_client")
            return JSONResponse(content={"status": True, "message": "Mensaje del sistema ignorado"})

        inbound_event_timestamp = parse_chat2desk_event_timestamp(payload.get("event_time"))
        if inbound_event_timestamp is not None:
            event_age_seconds = current_time - inbound_event_timestamp
            if event_age_seconds > STALE_INBOUND_EVENT_MAX_AGE_SECONDS:
                logger.warning(
                    "🚫 [STALE INBOUND] Ignorando inbound viejo para %s uid=%s event_time=%s age_seconds=%.1f max_age_seconds=%s body=%s",
                    from_number,
                    uid,
                    payload.get("event_time"),
                    event_age_seconds,
                    STALE_INBOUND_EVENT_MAX_AGE_SECONDS,
                    (body or "")[:120],
                )
                log_operational_decision_trace(
                    from_number,
                    "stale_inbound_event_ignored",
                    uid=uid,
                    inbound_event_time=payload.get("event_time"),
                    event_age_seconds=event_age_seconds,
                    body_preview=(body or "")[:240],
                )
                return JSONResponse(content={"status": True, "message": "Mensaje viejo ignorado"})

        if from_number in bot_returned_at and inbound_event_timestamp is not None:
            return_timestamp = bot_returned_at[from_number]
            delta_seconds = inbound_event_timestamp - return_timestamp
            if inbound_event_timestamp <= (return_timestamp + STALE_RETURN_EVENT_TOLERANCE_SECONDS):
                logger.warning(
                    "🧭 [RETURN FILTER] decision=stale from_number=%s uid=%s "
                    "return_event_time=%s inbound_event_time=%s delta_seconds=%.3f tolerance_seconds=%.3f",
                    from_number,
                    uid,
                    format_event_timestamp_for_log(return_timestamp),
                    format_event_timestamp_for_log(inbound_event_timestamp),
                    delta_seconds,
                    STALE_RETURN_EVENT_TOLERANCE_SECONDS,
                )
                logger.warning(
                    "🚫 [RETURN STALE EVENT] Ignorando inbound viejo/reentregado para %s "
                    "(event_time=%s, return_to_bot=%s, uid=%s)",
                    from_number,
                    payload.get("event_time"),
                    datetime.fromtimestamp(return_timestamp).isoformat(),
                    uid,
                )
                log_operational_decision_trace(
                    from_number,
                    "stale_inbound_after_return_to_bot",
                    uid=uid,
                    inbound_event_time=payload.get("event_time"),
                    return_timestamp=return_timestamp,
                    body_preview=(body or "")[:240],
                )
                return JSONResponse(content={"status": True, "message": "Mensaje viejo ignorado tras return-to-bot"})

            del bot_returned_at[from_number]
            logger.info(
                "🧭 [RETURN FILTER] decision=fresh from_number=%s uid=%s "
                "return_event_time=%s inbound_event_time=%s delta_seconds=%.3f tolerance_seconds=%.3f",
                from_number,
                uid,
                format_event_timestamp_for_log(return_timestamp),
                format_event_timestamp_for_log(inbound_event_timestamp),
                delta_seconds,
                STALE_RETURN_EVENT_TOLERANCE_SECONDS,
            )
            logger.info(f"✅ [RETURN FRESH EVENT] Primer inbound nuevo aceptado para {from_number} después de -bot")

        # Deduplicar mensajes entrantes solo cuando ya exista evidencia de entrega exitosa.
        # Si el primer intento guardó el inbound pero falló antes de responder, debemos permitir el retry.
        if has_successful_delivery_marker_for_inbound_uid(db, uid):
            logger.warning(
                "🚫 [PERSISTED DUPLICATE] Ignorando inbound repetido ya entregado para %s uid=%s event_time=%s body=%s",
                from_number,
                uid,
                payload.get("event_time"),
                (body or "")[:120],
            )
            log_operational_decision_trace(
                from_number,
                "persisted_duplicate_inbound_ignored",
                uid=uid,
                inbound_event_time=payload.get("event_time"),
                body_preview=(body or "")[:240],
                dedup_basis="successful_delivery_marker",
            )
            return JSONResponse(content={"status": True, "message": "Mensaje duplicado persistente ignorado"})

        if has_persisted_whatsapp_message_uid(db, uid):
            logger.warning(
                "♻️ [PERSISTED RETRY] Reintentando inbound previamente guardado sin marker de entrega para %s uid=%s event_time=%s body=%s",
                from_number,
                uid,
                payload.get("event_time"),
                (body or "")[:120],
            )
            log_operational_decision_trace(
                from_number,
                "persisted_inbound_retry_allowed",
                uid=uid,
                inbound_event_time=payload.get("event_time"),
                body_preview=(body or "")[:240],
            )

        if processed_message_ids.contains(uid):
            logger.debug(f"Ignorando mensaje duplicado con id={uid} antes de procesar flujos")
            return JSONResponse(content={"status": True, "message": "Mensaje duplicado ignorado"})

        processed_message_ids.add(uid)
        if len(processed_message_ids) > 1000:
            processed_message_ids.clear()
            processed_message_ids.add(uid)

        reply_context = extract_reply_context(payload)
        # 🆕 PROCESAR RESPUESTA SI ES DETECTADA
        if reply_context['is_reply']:
            if reply_context.get('is_quoted', False):
                logger.critical(f"📨 [QUOTED DETECTED] Usuario {from_number} citó: '{reply_context['original_message'][:30]}...' y respondió: '{reply_context['user_response']}'")
                
                # 🎯 CASO ESPECIAL: HSM + OK = Activar evaluación manualmente
                if ('@HSM@' in reply_context.get('original_message', '') and 
                    reply_context.get('user_response', '').upper() == 'OK'):
                    
                    try:
                        logger.critical(f"🎯 [HSM+OK QUOTED] ===== INICIANDO PROCESAMIENTO =====")
                        logger.critical(f"🎯 [HSM+OK QUOTED] from_number: {from_number}")
                        logger.critical(f"🎯 [HSM+OK QUOTED] client_id: {client_id}")
                        logger.critical(f"🎯 [HSM+OK QUOTED] channel_id: {channel_id}")
                        
                        # 🛠️ LIMPIAR Y PROCESAR MENSAJE HSM
                        original_message = reply_context['original_message']
                        
                        # Extraer reporte ID de manera robusta
                        reporte_id = None
                        
                        # Método 1: Buscar líneas que sean solo números (4+ dígitos)
                        lines = original_message.replace('\r\n', '\n').split('\n')
                        logger.critical(f"🎯 [HSM+OK] Líneas encontradas: {lines}")
                        for line in lines:
                            line_clean = line.strip()
                            if line_clean.isdigit() and len(line_clean) >= 4:
                                reporte_id = line_clean
                                logger.critical(f"🎯 [HSM+OK] ID extraído por líneas: {reporte_id}")
                                break
                        
                        # Método 2: Fallback con regex
                        if not reporte_id:
                            import re
                            match = regex_module.search(r'\b(\d{4,})\b', original_message)
                            if match:
                                reporte_id = match.group(1)
                                logger.critical(f"🎯 [HSM+OK] ID extraído por regex: {reporte_id}")
                        
                        if not reporte_id:
                            logger.error(f"❌ [HSM+OK] No se pudo extraer ID del reporte")
                            logger.error(f"❌ [HSM+OK] Mensaje original: {original_message[:200]}...")
                            reporte_id = "UNKNOWN"
                        
                        logger.critical(f"🎯 [HSM+OK] Activando evaluación para reporte {reporte_id}")
                        
                        # Configurar estado de evaluación
                        if from_number not in user_sessions:
                            user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
                        
                        session = user_sessions[from_number]
                        session.evaluation_state = EVALUATION_STATES["WAITING_RESOLUTION_RESPONSE"]  # DIRECTO A ESPERANDO RESPUESTA
                        session.evaluation_folio = reporte_id
                        session.evaluation_client_id = client_id
                        session.evaluation_channel_id = channel_id
                        session.update_activity()

                        logger.critical(f"🎯 [HSM+OK] ✅ Estado configurado:")
                        logger.critical(f"🎯 [HSM+OK]   - evaluation_state: {session.evaluation_state}")
                        logger.critical(f"🎯 [HSM+OK]   - evaluation_folio: {session.evaluation_folio}")
                        logger.critical(f"🎯 [HSM+OK]   - evaluation_client_id: {session.evaluation_client_id}")
                        logger.critical(f"🎯 [HSM+OK]   - evaluation_channel_id: {session.evaluation_channel_id}")
                        
                        # Enviar comentario de conclusión INMEDIATAMENTE
                        logger.critical(f"📤 [HSM+OK] Enviando comentario de conclusión para {reporte_id}")
                        await send_conclusion_comment_and_image(client_id, channel_id, reporte_id, transport)
                        
                        # Esperar un momento antes de la pregunta de evaluación
                        await asyncio.sleep(2)
                        
                        # Enviar pregunta de evaluación
                        logger.critical(f"📤 [HSM+OK] Enviando pregunta de evaluación")
                        validation_message = "¿Está de acuerdo con la resolución? Por favor responda *Sí* o *No*."
                        await send_chat2desk_message_direct(client_id, channel_id, validation_message, transport)
                        
                        logger.critical(f"✅ [HSM+OK] Evaluación iniciada exitosamente para reporte {reporte_id}")
                        return JSONResponse(content={"status": True, "message": "Evaluación iniciada por OK citado"})
                        
                    except Exception as e:
                        logger.error(f"Error procesando HSM+OK citado: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        try:
                            # Fallback mínimo
                            validation_message = "¿Está de acuerdo con la resolución? Por favor responda *Sí* o *No*."
                            await send_chat2desk_message_direct(client_id, channel_id, validation_message, transport)
                            
                            # Configurar estado básico
                            if from_number not in user_sessions:
                                user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
                            
                            session = user_sessions[from_number]
                            session.evaluation_state = EVALUATION_STATES["WAITING_RESOLUTION_RESPONSE"]
                            session.evaluation_folio = "UNKNOWN"
                            session.evaluation_client_id = client_id
                            session.evaluation_channel_id = channel_id
                            session.update_activity()
                            
                            return JSONResponse(content={"status": True, "message": "Evaluación iniciada (fallback)"})
                        except Exception as fallback_error:
                            logger.error(f"❌ [FALLBACK ERROR] Error crítico: {str(fallback_error)}")
                            return JSONResponse(content={"status": False, "error": "Error crítico en HSM+OK"})  

            
            # Si no hay sesión de reporte pero la respuesta sugiere actividad de reporte, crearla
            if (from_number not in report_sessions and 
                (should_create_report_session(body, "") or 
                any(keyword in reply_context.get('original_message', '').lower() 
                    for keyword in ['reporte', 'problema', 'bache', 'luminaria', 'basura', 'número', 'numero', 'calle', 'colonia']))):
                create_or_update_report_session(from_number)
                logger.critical(f"🎯 [REPLY SESSION] Sesión de reporte creada por contexto de reply")

        # ✅ SOLO evaluar respuestas del ciudadano, nunca mensajes salientes del bot
        if from_number in user_sessions:
            session = user_sessions[from_number]
            if hasattr(session, 'evaluation_state') and session.evaluation_state:
                evaluation_text = get_effective_user_message_text(body, reply_context)
                evaluation_handled = await handle_evaluation_response(
                    from_number, evaluation_text, client_id, channel_id, transport
                )
                if evaluation_handled:
                    return JSONResponse(content={"status": True, "message": "Evaluation response processed"})
        
        # Extraer información del payload de Chat2Desk
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        message_id = payload.get('message_id')
        body = payload.get('text', '')
        # Handle None values in body
        if body is None:
            body = ""
            logger.debug("Message with None body detected, setting to empty string")


        # Get recent AI messages for this number to check for echoes
        recent_ai_messages = []
        if from_number in user_sessions:
            # Get last 3 AI messages from the conversation history
            for msg in user_sessions[from_number].history.messages[-6:]:  # Check last 6 messages
                if isinstance(msg, AIMessage):
                    recent_ai_messages.append(msg.content)
        
        # Check if this is our own message being reflected back
        if is_bot_generated_message(body, recent_ai_messages):
            logger.info(f"Detected echo of our own message: '{body[:50]}...' - Ignoring")
            return JSONResponse(content={"status": True, "message": "Echo message ignored"})
        
        # Check again specifically for image receipt messages
        if "[IMAGE_RECEIPT]" in body or (("he recibido" in body.lower() and "imagen" in body.lower()) and 
                                         ("total" in body.lower() or "puedes enviar" in body.lower())):
            logger.info(f"Detected image receipt message echo: '{body[:50]}...' - Ignoring")
            return JSONResponse(content={"status": True, "message": "Image receipt message ignored"})
        
        logger.debug(f"Datos recibidos: chat_id={chat_id}, sender_name={sender_name}, body={body}, "
                     f"from_number={from_number}, message_type={message_type}, uid={uid}")
        


        # Variables para ubicación, imagen y audio
        address = None
        latitude, longitude = None, None
        photo_url = None
        audio_url = None
        image_description = None
        
        # Verificación del tipo de contenido en el mensaje
        if payload.get("coordinates"):
            # Procesamiento de ubicación
            coords = payload.get("coordinates")
            logger.debug(f"Formato de coordenadas recibidas: {coords}")
            
            # Manejar tanto formato con coma como con espacio
            if isinstance(coords, str):
                if "," in coords:
                    latitude, longitude = coords.split(",")
                elif " " in coords:
                    longitude, latitude = coords.split(" ")  # Nota: en tu payload, primero viene la longitud
                else:
                    logger.error(f"Formato de coordenadas desconocido: {coords}")
                    latitude, longitude = None, None
                    
                if latitude and longitude:
                    try:
                        # Asegurarse que las coordenadas son números flotantes
                        latitude = float(latitude.strip())
                        longitude = float(longitude.strip())
                        
                        # Convertir la latitud y longitud a dirección
                        address = await latlong_to_address(latitude, longitude)
                        # Verificar si hay un contexto de búsqueda de oficinas gubernamentales
                        # Esto puede ser determinado por mensajes previos del usuario o una variable de sesión
                        office_search_context = False
                        office_type = None
                        
                        # Si el usuario tiene una sesión activa, podemos verificar los mensajes recientes
                        if from_number in user_sessions:
                            recent_messages = user_sessions[from_number].history.messages[-5:]  # Últimos 5 mensajes
                            for msg in recent_messages:
                                if isinstance(msg, HumanMessage):
                                    msg_content = msg.content.lower()
                                    
                                    # Buscar referencias a oficinas gubernamentales
                                    if any(term in msg_content for term in ["registro civil", "acta", "nacimiento", "matrimonio", "defunción"]):
                                        office_search_context = True
                                        office_type = "registro_civil"
                                        break
                                        
                                    if any(term in msg_content for term in ["centro comunitario", "comunitario", "cursos", "talleres", "actividades"]):
                                        office_search_context = True
                                        office_type = "centro_comunitario"
                                        break
                                        
                                    # Buscar indicios de querer saber la más cercana
                                    if any(term in msg_content for term in ["cerca", "cercana", "cercano", "próxima", "próximo", "oficina"]):
                                        # Si no se ha identificado un tipo específico pero el usuario mencionó algo de cercanía
                                        if "registro" in msg_content or "acta" in msg_content:
                                            office_search_context = True
                                            office_type = "registro_civil"
                                            break
                                        elif "centro" in msg_content or "comunitario" in msg_content:
                                            office_search_context = True
                                            office_type = "centro_comunitario"
                                            break
                        
                        if office_search_context and office_type:
                            try:
                                result = await find_nearest_government_office(
                                    latitude=float(latitude),
                                    longitude=float(longitude),
                                    office_type=office_type
                                )
                                
                                if result.get("success", False):
                                    nearest = result.get("nearest_office", {})
                                    
                                    # Crear respuesta con la oficina más cercana
                                    office_type_name = "Registro Civil" if office_type == "registro_civil" else "Centro Comunitario"
                                    body = f"He encontrado el {office_type_name} más cercano a tu ubicación:\n\n"
                                    body += f"🏢 *{nearest.get('name', 'No disponible')}*\n"
                                    body += f"📍 Dirección: {nearest.get('address', 'No disponible')}\n"
                                    body += f"📞 Teléfono: {nearest.get('phone', 'No disponible')}\n"
                                    body += f"🕒 Horario: {nearest.get('schedule', 'No disponible')}\n"
                                    body += f"🚶 Distancia: {nearest.get('distance', 'No disponible')} km\n\n"
                                    
                                    # Añadir recomendaciones alternativas (las siguientes 2 más cercanas)
                                    all_offices = result.get("all_offices", [])
                                    if len(all_offices) > 1:
                                        body += "Otras opciones cercanas:\n\n"
                                        for i, office in enumerate(all_offices[1:3], 1):
                                            if isinstance(office, dict):  # Verificar que office sea un diccionario
                                                body += f"{i}. *{office.get('name', 'No disponible')}* - {office.get('distance', 'No disponible')} km\n"
                                                body += f"   📍 {office.get('address', 'No disponible')}\n"
                                    # IMPORTANTE: Enviar este mensaje directamente al usuario sin pasar por el LLM
                                    # Guardar el mensaje en la BD
                                    logger.debug(f"Guardando respuesta directa con información de oficina cercana: {body[:30]}...")
                                    assistant_message = Message(
                                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        senderName="Assistant",
                                        message=body,
                                        number=from_number,
                                        uid=uid,
                                        direction="outbound",
                                        mtype="text",
                                        source="whatsapp"
                                    )
                                    db.Insert(assistant_message)
                                    await manage_message_history(db, from_number)
                                    
                                    # Enviar mensaje directamente a través de Chat2Desk
                                    api_token = os.getenv("CHAT2DESK_API_TOKEN")
                                    chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                                    
                                    headers = {
                                        "Authorization": api_token,
                                        "Content-Type": "application/json"
                                    }
                                    
                                    data = {
                                        "client_id": client_id,
                                        "channel_id": channel_id,
                                        "transport": transport,
                                        "text": body
                                    }

                                    log_chat2desk_outbound_attempt(
                                        "nearest_office_direct",
                                        data,
                                        from_number=from_number,
                                        message_id=message_id,
                                    )
                                    direct_response = requests.post(chat2desk_url, json=data, headers=headers)
                                    log_chat2desk_outbound_response(
                                        "nearest_office_direct",
                                        direct_response,
                                        from_number=from_number,
                                        message_id=message_id,
                                    )
                                    if direct_response.status_code == 200:
                                        logger.debug(f"Información de oficina cercana enviada exitosamente a Chat2Desk")
                                        # No continuar con el procesamiento normal del LLM
                                        return JSONResponse(content={"status": True, "message": "Respuesta directa enviada por Chat2Desk"})
                                    else:
                                        logger.error(f"Error al enviar mensaje directo a Chat2Desk: {direct_response.status_code} - {direct_response.text}")
                                        # Continuar con el flujo normal si falla el envío directo
                                else:
                                    body = f"Lo siento, tuve un problema al buscar la oficina más cercana. {result.get('error', '')}"
                            except Exception as e:
                                logger.error(f"Error al buscar oficina cercana: {str(e)}")
                                body = f"Lo siento, ocurrió un error al buscar oficinas cercanas. Por favor, intenta de nuevo más tarde."
                        else:
                            # Respuesta estándar para ubicación (mantener el comportamiento actual)
                            body = f"Ubicación recibida: {address}\nLatitud: {latitude}, Longitud: {longitude}"
                            
                            # Si hay un reporte en progreso, actualizar la ubicación
                            if from_number in report_sessions:
                                report_sessions[from_number]["location"] = address
                                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                            
                    except Exception as e:
                        logger.error(f"Error al procesar coordenadas: {str(e)}")
                        body = f"Ubicación recibida: Latitud {latitude}, Longitud {longitude}"
                    
                    logger.debug(f"Mensaje con ubicación: latitude={latitude}, longitude={longitude}, address={address if 'address' in locals() else 'No disponible'}")

        elif payload.get("audio"):
            # Procesamiento de audio
            audio_url = payload.get("audio")
            body = TranscribeOGG(audio_url, config["language"])
            logger.debug(f"Audio transcrito: {body}")

        elif payload.get("photo"):
            # Procesamiento de imagen
            photo_url = payload.get("photo")
            if photo_url:
                previous = get_user_answer(from_number, "selection8") or ""
                updated_list = [url.strip() for url in previous.split(",") if url.strip()]
                updated_list.append(photo_url)
                new_value = ",".join(updated_list)
                save_user_answer(from_number, "selection8", new_value)
                logger.info(f"[{from_number}] Imagen añadida a selection8: {photo_url}")
                try:
                    # Analizar la imagen con rate limiting
                    image_description = await analyze_image_with_rate_limit(client, photo_url)

                    # Almacenar en la sesión de reporte usando la estructura centralizada
                    create_or_update_report_session(from_number)
                    
                    # Añadir esta imagen al reporte en progreso - con verificación
                    if isinstance(photo_url, str) and (photo_url.startswith("http") or "storage.chat2desk.com" in photo_url):
                        # Asegurar que la sesión tenga la estructura completa
                        create_or_update_report_session(from_number)
                        # Asegurarse de que la imagen no esté duplicada
                        if photo_url not in report_sessions[from_number]["images"]:
                            report_sessions[from_number]["images"].append(photo_url)
                            report_sessions[from_number]["image_descriptions"].append(image_description)
                            report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                            
                            logger.info(f"Imagen #{len(report_sessions[from_number]['images'])} añadida al reporte para {from_number}")
                        else:
                            logger.warning(f"Imagen duplicada ignorada: {photo_url[:50]}...")
                    else:
                        logger.error(f"URL de imagen inválida: {str(photo_url)[:50]}...")
                    
                    num_images = len(report_sessions[from_number]["images"])
                    la_foto = report_sessions[from_number]["image_descriptions"][0]
                    if num_images == 1:
                        body = f"{sender_name} recibí tu imagen veo {la_foto}, y la he guardado para el reporte. Si deseas continuar con tu reporte, responde FIN. En caso de que tengas otra foto, por favor envíala."
                    else:
                        body = f"He recibido otra imagen (tienes {num_images} en total). Puedes seguir enviando imágenes o responde FIN cuando estés listo."
                    
                    logger.debug(f"Imagen añadida al reporte en progreso para {from_number}. Total: {num_images}")
                    
                    # Since this is an image-only message, we need to send our response right away
                    try:
                        # Store the bot's response in the database and conversation history
                        if from_number in user_sessions:
                            conversation_history = user_sessions[from_number].history
                            conversation_history.add_ai_message(body)
                        
                        # Create a message record
                        assistant_message = Message(
                            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            senderName="Assistant",
                            message=body,
                            number=from_number,
                            uid=uid,
                            direction="outbound",
                            mtype="text",
                            source="whatsapp"
                        )
                        db.Insert(assistant_message)
                        await manage_message_history(db, from_number)
                        
                        # Send the response to Chat2Desk
                        api_token = os.getenv("CHAT2DESK_API_TOKEN")
                        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                        
                        headers = {
                            "Authorization": api_token,
                            "Content-Type": "application/json"
                        }

                        data = {
                            "client_id": client_id,
                            "channel_id": channel_id,
                            "transport": transport,
                            "text": body
                        }

                        log_chat2desk_outbound_attempt(
                            "image_ack",
                            data,
                            from_number=from_number,
                            message_id=message_id,
                        )
                        response = requests.post(chat2desk_url, json=data, headers=headers)
                        log_chat2desk_outbound_response(
                            "image_ack",
                            response,
                            from_number=from_number,
                            message_id=message_id,
                        )

                        if response.status_code == 200:
                            logger.debug(f"Respuesta de imagen enviada exitosamente a Chat2Desk")
                            return JSONResponse(content={"status": True, "message": "Respuesta de imagen enviada por Chat2Desk"})
                        else:
                            logger.error(f"Error al enviar respuesta de imagen a Chat2Desk: {response.status_code} - {response.text}")
                    except Exception as e:
                        logger.error(f"Error al enviar respuesta de imagen: {str(e)}")
                        return JSONResponse(content={"error": f"Error al enviar respuesta de imagen: {str(e)}"}, status_code=500)
                    
                except requests.RequestException as e:
                    logger.error(f"Error al descargar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero no se pudo descargar. Por favor, intenta enviarla de nuevo."
                except Exception as e:
                    logger.error(f"Error al analizar la imagen: {str(e)}")
                    body = "Se recibió una imagen, pero hubo un problema al analizarla. El equipo técnico ha sido notificado."
            else:
                body = "Se recibió una notificación de imagen, pero no se encontró la URL de la imagen."
                logger.warning("No se pudo obtener la URL de la imagen del formulario de datos.")

        elif body and from_number in report_sessions:
            detect_and_store_user_data_with_real_streets_and_colonies(from_number, body)
            logger.debug(f"[{from_number}] Revisión anticipada de datos estructurados: '{body[:50]}...'")

        # Now let's fix the report finalization check in the WhatsApp endpoint
        elif body and from_number in report_sessions and report_sessions[from_number]["images"]:
            # El usuario ya ha enviado imágenes, este texto podría ser información del reporte
            
            # Log the message to help with debugging
            logger.debug(f"Processing potential report data for {from_number}: '{body[:50]}...'")
            
            # First, ensure this isn't a bot-generated message being echoed back
            is_bot_message = False
            
            # Check for specific image receipt markers
            if "[IMAGE_RECEIPT]" in body or ("he recibido" in body.lower() and "imagen" in body.lower()):
                is_bot_message = True
                logger.warning(f"Ignoring bot image receipt message: '{body[:50]}...'")
            
            # For other messages, check if they match recent bot messages
            if not is_bot_message and from_number in user_sessions:
                recent_messages = user_sessions[from_number].history.messages[-3:]  # Last 3 messages
                for msg in recent_messages:
                    if isinstance(msg, AIMessage) and (msg.content in body or body in msg.content):
                        is_bot_message = True
                        logger.warning(f"Message appears to be a bot message echo: '{body[:50]}...'")
                        break
            if not is_bot_message:
                detect_and_store_user_data_with_real_streets_and_colonies(from_number, body)
            
            if is_bot_message:
                # Skip processing if this appears to be from the bot
                return JSONResponse(content={"status": True, "message": "Bot message echo ignored"})
            
            # Now check if this is providing location or requesting finalization
            is_location = any(keyword in body.lower() for keyword in ["ubicación", "dirección", "calle", "avenida", "colonia", "avenue", "numero", "número"])
            is_finalization = is_finalization_message(body, from_number)

            
            # Log the classification for debugging
            logger.debug(f"Message classification - Is location: {is_location}, Is finalization: {is_finalization}")
            
            if is_location:
                # Es información de ubicación
                report_sessions[from_number]["location"] = body
                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
                body = f"Ubicación registrada: {body}. Para finalizar tu reporte con las imágenes que has enviado, avísame cuando estés listo."
            elif is_finalization:
                # Generate a unique request ID for this report finalization request
                request_id = f"{from_number}-{int(datetime.now().timestamp())}"
                logger.info(f"Report finalization request {request_id} received")
                
                # En lugar de procesar directamente, enviar un mensaje especial al modelo
                finalization_prompt = "El usuario quiere finalizar el reporte. " + \
                         "Por favor, verifica que has recopilado toda la información necesaria " + \
                         "(asunto, nombre, calle, número, colonia) y llama a la función save_client_selection " + \
                         "con los datos completos. Si falta algún dato, solicítalo antes de proceder."
                
                # Añadir este mensaje al historial como si fuera un mensaje del sistema
                if from_number in user_sessions:
                    conversation_history = user_sessions[from_number].history
                    conversation_history.add_ai_message(f"[SISTEMA: {finalization_prompt}]")

                # El usuario quiere finalizar el reporte
                images = report_sessions[from_number]["images"]
                descriptions = report_sessions[from_number]["image_descriptions"]

                if fotos_urls:
                    for foto in fotos_urls:
                        if foto not in images:
                            images.append(foto)
                            descriptions.append("Imagen adicional")  # Descripción genérica
                
                # Deduplicate images to ensure no duplicates
                unique_images = []
                unique_descriptions = []
                img_set = set()
                
                for i, img in enumerate(images):
                    if img not in img_set:
                        img_set.add(img)
                        unique_images.append(img)
                        if i < len(descriptions):
                            unique_descriptions.append(descriptions[i])
                
                logger.info(f"After deduplication: {len(unique_images)} of {len(images)} images remain")
                
                # Use the location stored in the report session or the current message as fallback
                user_location = report_sessions[from_number]["location"] or body or "ubicación no especificada"
                
                # Usar la función centralizada para procesar el reporte
                result = await process_and_save_report(from_number, user_location, unique_images, unique_descriptions)
                
                if result['status'] == 'in_progress':
                    body = result['message']
                elif result['status'] == 'duplicate':
                    body = result['message']
                elif result['status'] == 'no_images':
                    body = result['message']
                elif result['status'] == 'validation_block':
                    body = result['message']
                elif result['status'] == 'error':
                    body = f"Lo siento, hubo un error al finalizar tu reporte: {result['message']}. Por favor, intenta nuevamente."
                elif result['status'] == 'success':
                    # El reporte se creó exitosamente
                    folio = result['folio']
                    logger.info(f"Successfully created report with folio {folio} for request {request_id}")

                    mark_report_as_completed(from_number)

                    asyncio.create_task(delayed_cleanup_report_session(from_number, 30))

                    # Limpiar la sesión de reporte después de finalizar
                    if from_number in report_sessions:
                        del report_sessions[from_number]
                                            
                    # Importante: Construir un mensaje informativo que *NO* requiera acción adicional del usuario
                    image_text = f"con {len(unique_images)} imágenes " if unique_images else ""
                    body = f"Tu reporte ha sido generado con éxito. El número de folio para tu reporte es {folio}. Tu reporte {image_text}ha sido enviado al sistema. Agradecemos mucho tu colaboración. Estamos para servirte"
                    
                    # Verificar que el mensaje no esté vacío 
                    if not body or len(body.strip()) == 0:
                        body = f"Tu reporte ha sido generado exitosamente. Agradecemos tu colaboración. Estamos para servirte."

                    # Crear y guardar un mensaje de sistema explicando lo que ocurrió
                    img_count = f"que incluye {len(unique_images)} imágenes " if unique_images else ""
                    system_notification = Message(
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        senderName="System",
                        message=f"[SISTEMA: Se generó el reporte con folio {folio} {img_count}de la ubicación '{user_location}'. El reporte ha sido enviado al sistema.]",
                        number=from_number,
                        uid=f"system-{request_id}",
                        direction="system",
                        mtype="text",
                        source="whatsapp"
                    )
                    db.Insert(system_notification)

                    # IMPORTANTE: Ahora vamos a enviar este mensaje directamente a través de Chat2Desk
                    # para evitar que siga el flujo normal y cause una transferencia a humano
                    try:
                        # Guardar la respuesta en el historial y en la base de datos como mensaje del asistente
                        assistant_message = Message(
                            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            senderName="Assistant",
                            message=body,
                            number=from_number,
                            uid=f"success-report-{request_id}",
                            direction="outbound",
                            mtype="text",
                            source="whatsapp"
                        )
                        db.Insert(assistant_message)
                        await manage_message_history(db, from_number)
                        
                        # Enviar directamente el mensaje a través de Chat2Desk
                        api_token = os.getenv("CHAT2DESK_API_TOKEN")
                        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
                        
                        headers = {
                            "Authorization": api_token,
                            "Content-Type": "application/json"
                        }

                        data = {
                            "client_id": client_id,
                            "channel_id": channel_id,
                            "transport": transport,
                            "text": body
                        }

                        log_chat2desk_outbound_attempt(
                            "report_finalization_direct",
                            data,
                            from_number=from_number,
                            message_id=message_id,
                        )
                        response = requests.post(chat2desk_url, json=data, headers=headers)
                        log_chat2desk_outbound_response(
                            "report_finalization_direct",
                            response,
                            from_number=from_number,
                            message_id=message_id,
                        )

                        if response.status_code == 200:
                            logger.debug(f"Mensaje de finalización enviado directamente a través de Chat2Desk")
                        else:
                            logger.error(f"Error al enviar mensaje directo a Chat2Desk: {response.status_code} - {response.text}")
                    except Exception as e:
                        logger.error(f"Error al enviar mensaje de finalización directo: {str(e)}")
                    
                    # IMPORTANTE: Devolver un resultado sin mensaje de texto para evitar el procesamiento posterior
                    # Esto evitará que el sistema envíe otro mensaje o confunda el texto de respuesta como entrada
                    return {
                        'status': 'success',
                        'message': "",  # Vacío para evitar procesamiento posterior
                        'folio': folio
                    }

                    
    # Continuar con el procesamiento normal
    except KeyError as e:
        logger.error(f"Falta el parámetro requerido: {e}")
        return JSONResponse(content={"error": f"Falta el parámetro {str(e)}"}, status_code=400)
    except Exception as e:
        logger.error(f"Error al procesar el payload: {str(e)}")
        return JSONResponse(content={"error": f"Error al procesar el payload: {str(e)}"}, status_code=400)

    # Validación básica para evitar procesar mensajes mal formados
    if not from_number or not body:
        logger.warning("Mensaje recibido sin número de teléfono o cuerpo del mensaje")
        return JSONResponse(content={"status": False, "error": "Datos incompletos"}, status_code=400)
            
    # ✅ BLOQUEAR MENSAJES QUE PARECEN RESPUESTAS DE EVALUACIÓN
    if body and body.strip().upper() == "OK" and from_number in user_sessions:
        session = user_sessions[from_number]
        # Si acabamos de enviar un HSM (últimos 2 minutos), ignorar el OK
        current_time = datetime.now().timestamp()
        if hasattr(session, 'last_hsm_time') and session.last_hsm_time is not None and (current_time - session.last_hsm_time) < 120:
            logger.critical(f"🚫 [OK BLOCKED] OK ignorado para {from_number} - posible respuesta de evaluación")
            return JSONResponse(content={"status": True, "message": "OK response ignored during evaluation"})
        
    # 🚫 VERIFICAR SI EL NÚMERO ESTÁ EN COOLDOWN POR INACTIVIDAD
    current_time = datetime.now().timestamp()
    if from_number in closed_by_inactivity:
        cooldown_expiry = closed_by_inactivity[from_number]
        if current_time < cooldown_expiry:
            remaining_minutes = (cooldown_expiry - current_time) / 60
            logger.critical(f"🚫 [COOLDOWN] {from_number} está en cooldown por inactividad. Faltan {remaining_minutes:.1f} minutos")
            return JSONResponse(content={"status": True, "message": "Usuario en cooldown por inactividad"})
        else:
            # Cooldown expirado, remover del diccionario
            del closed_by_inactivity[from_number]
            logger.critical(f"✅ [COOLDOWN EXPIRED] {from_number} cooldown expirado, puede reactivarse")

    # Crear o actualizar la sesión del usuario
    if from_number not in user_sessions:
        logger.debug(f"Creando nueva sesión para el usuario: {from_number}")
        user_sessions[from_number] = WhatsAppSession(ChatMessageHistory())
    session = user_sessions[from_number]
    session.update_activity()
    conversation_history = session.history

    # Recuperar mensajes históricos desde la base de datos y agregarlos al historial
    try:
        logger.debug(f"Recuperando mensajes históricos para el número: {from_number}")

        should_reset_context_after_human = from_number in recently_returned_to_bot

        # Obtener mensajes ordenados por tiempo (los más antiguos primero)
        messages_db = [] if should_reset_context_after_human else (
            db.Search(Message(number=from_number, source="whatsapp"), order='asc', limit=50) or []
        )
        last_outbound_message = next(
            (msg.message for msg in reversed(messages_db) if msg.direction == "outbound" and msg.message),
            "",
        )

        # Limpiar el historial antes de agregar mensajes para evitar duplicados
        conversation_history.messages.clear()

        if should_reset_context_after_human:
            logger.critical(
                "🧹 [RETURN CONTEXT RESET] Reiniciando historial conversacional para %s tras regreso desde agente humano",
                from_number,
            )
        else:
            # Añadir los mensajes al historial en el orden correcto
            for msg in messages_db:
                if msg.direction == "inbound":
                    conversation_history.add_user_message(msg.message)
                    logger.debug(f"Mensaje histórico (usuario): {msg.message[:30]}...")
                elif msg.direction == "outbound":
                    conversation_history.add_ai_message(msg.message)
                    logger.debug(f"Mensaje histórico (asistente): {msg.message[:30]}...")
            
    except Exception as e:
        logger.error(f"Error al recuperar mensajes históricos: {str(e)}")

    # Agregar mensaje actual del usuario al historial y guardarlo en la base de datos
    conversation_history.add_user_message(body)

    if assistant_asked_for_optional_image(last_outbound_message):
        create_or_update_report_session(from_number)
        with report_sessions_lock:
            report_sessions[from_number]["image_prompted"] = True

            decision = classify_image_decision_response(body)
            if decision:
                report_sessions[from_number]["image_decision"] = decision
                logger.critical(
                    "🖼️ [IMAGE DECISION] %s respondió sobre imagen: %s",
                    from_number,
                    decision,
                )

    if from_number in report_sessions:
        create_or_update_report_session(from_number)
        with report_sessions_lock:

            if assistant_asked_if_emergency(last_outbound_message):
                emergency_answer = classify_emergency_response(body)
                if emergency_answer is not None:
                    report_sessions[from_number]["declared_emergency"] = emergency_answer
                    logger.critical(
                        "🚨 [EMERGENCY FLAG] %s respondió emergencia=%s",
                        from_number,
                        emergency_answer,
                    )

    user_message = Message(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        senderName=sender_name,
        message=body,
        number=from_number,
        uid=uid,
        direction="inbound",
        mtype="text",
        source="whatsapp",
        latitude=latitude,
        longitude=longitude
    )
    logger.debug(f"Guardando mensaje del usuario en BD: {body[:30]}...")
    db.Insert(user_message)
    await manage_message_history(db, from_number)

    message_id = payload.get('message_id')

    if is_explicit_human_handoff_request(body):
        logger.critical(
            "🔀 [DIRECT TRANSFER MATCH] %s solicitó atención humana con mensaje: %s",
            from_number,
            body,
        )
        response_content = "Claro, te transfiero con un agente humano, por favor espera un momento."
        transfer_result = None

        try:
            if not message_id:
                raise ValueError("No se encontró message_id en el payload para transferir")

            expiration_time = datetime.now().timestamp() + transfer_timeout
            transferred_numbers[from_number] = expiration_time

            transfer_result = await transfer_to_group(
                message_id=message_id,
                group_id=None,
                reason="Solicitud explícita del usuario para hablar con humano",
            )

            logger.critical(
                "✅ [DIRECT TRANSFER] %s solicitado por usuario. Resultado: %s",
                from_number,
                transfer_result,
            )

            transfer_note = Message(
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                senderName="System",
                message=f"[SYSTEM] Transferencia directa ejecutada - message_id: {message_id}",
                number=from_number,
                uid=f"direct-transfer-{datetime.now().timestamp()}",
                direction="system",
                mtype="text",
                source="whatsapp"
            )
            db.Insert(transfer_note)

        except Exception as transfer_error:
            logger.error(f"❌ [DIRECT TRANSFER] Error ejecutando transferencia: {str(transfer_error)}")
            if from_number in transferred_numbers:
                del transferred_numbers[from_number]
            response_content = "Estoy teniendo problemas técnicos para transferirte en este momento. Por favor, intenta de nuevo."

        assistant_message = Message(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            senderName="Assistant",
            message=response_content,
            number=from_number,
            uid=f"assistant-{datetime.now().timestamp()}",
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )
        db.Insert(assistant_message)
        await manage_message_history(db, from_number)

        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": response_content
        }

        outbound_dedup_key = build_outbound_response_dedup_key(
            from_number=from_number,
            message_id=message_id,
            response_content=response_content,
        )
        if recent_outbound_response_keys.contains(outbound_dedup_key):
            logger.warning(
                "🚫 [OUTBOUND DEDUP] Respuesta duplicada bloqueada para %s con message_id=%s",
                from_number,
                message_id,
            )
            log_operational_decision_trace(
                from_number,
                "outbound_duplicate_blocked",
                message_id=message_id,
                response_preview=response_content[:300],
            )
            return JSONResponse(content={"status": True, "message": "Respuesta duplicada bloqueada"})

        recent_outbound_response_keys.add(outbound_dedup_key)

        log_chat2desk_outbound_attempt(
            "whatsapp_main",
            data,
            from_number=from_number,
            message_id=message_id,
        )
        response = requests.post(chat2desk_url, json=data, headers=headers, timeout=30)
        log_chat2desk_outbound_response(
            "whatsapp_main",
            response,
            from_number=from_number,
            message_id=message_id,
        )

        if response.status_code == 200:
            persist_successful_delivery_marker(db, from_number, uid, message_id)
            logger.debug("Respuesta enviada exitosamente a Chat2Desk")
            return JSONResponse(
                content={
                    "status": True,
                    "message": "Transferencia directa procesada",
                    "transfer_result": transfer_result,
                }
            )

        logger.error(
            "Error al enviar mensaje de transferencia directa a Chat2Desk: %s - %s",
            response.status_code,
            response.text,
        )
        return JSONResponse(
            content={
                "status": False,
                "error": "Error enviando respuesta de transferencia directa",
                "transfer_result": transfer_result,
            },
            status_code=500,
        )
    mexico_tz = pytz.timezone('America/Mexico_City')
    current_datetime = datetime.now(mexico_tz)
    date_string = current_datetime.strftime("%Y-%m-%d")
    hour = current_datetime.strftime("%I:%M:%S %p")
    fotos_urls = report_sessions[from_number]["images"] if from_number in report_sessions and report_sessions[from_number]["images"] else []

    # Aplanar cualquier lista anidada y asegurar que todo sean strings
    flat_fotos = []
    for item in fotos_urls:
        if isinstance(item, list):
            # Si es una lista, agregar cada elemento
            flat_fotos.extend([str(x) for x in item if x])  # Convertir a string y filtrar vacíos
        elif isinstance(item, str) and item.strip():
            # Si es string no vacío, agregarlo
            flat_fotos.append(item.strip())

    # Crear el string final
    fotos_string = ",".join(flat_fotos) if flat_fotos else ""
    
    if from_number in report_sessions:
        # Actualizar la sesión con los datos del contexto LLM
        with report_sessions_lock:
            session = report_sessions[from_number]
            
            # Guardar todos los datos que el LLM tiene disponibles
            session["llm_context"] = {
                "message_id": message_id,
                "yoga_number": from_number,
                "sender_name": sender_name,
                "address": address if 'address' in locals() else "Ubicación no disponible",
                "fotos_string": fotos_string,
                "date": date_string,
                "hour": hour,
                "uid": uid
            }
            
            # También actualizar timestamp
            session["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
            
            logger.critical(f"🎯 [LLM CONTEXT] Datos guardados para {from_number}:")
            logger.critical(f"🎯 [LLM CONTEXT] - Nombre: {sender_name}")
            logger.critical(f"🎯 [LLM CONTEXT] - Dirección: {address if 'address' in locals() else 'No disponible'}")
            logger.critical(f"🎯 [LLM CONTEXT] - Fotos: {len(flat_fotos)} URLs")
            logger.critical(f"🎯 [LLM CONTEXT] - Fecha: {date_string} {hour}")

    # Después crear el system_prompt como siempre:
    system_prompt = system_message.format(
        customer_name=sender_name,
        call_sid=uid,
        date2=date_string,
        yoga_number=from_number,
        now=hour,
        folio="Pendiente de generar",
        address=address if 'address' in locals() else "No he recibido ubicación",
        image_description=image_description if 'image_description' in locals() else "No se ha recibido ninguna imagen",
        fotos=fotos_string
    )
    # Debug log para entender qué está pasando
    logger.debug(f"Fotos originales: {fotos_urls}")
    logger.debug(f"Fotos aplanadas: {flat_fotos}")
    logger.debug(f"Fotos string final: {fotos_string}")

    try:
        # Crear el prompt con el historial de mensajes
        system_prompt = system_message.format(customer_name=sender_name,call_sid=uid,date2=date_string,
            yoga_number=user_message.number,
            now=hour,
            folio="Pendiente de generar",
            address=address if 'address' in locals() else "No he recibido ubicación",
            image_description=image_description if 'image_description' in locals() else "No se ha recibido ninguna imagen",
            fotos=fotos_string
        )
        # Añadir instrucción para evitar generación automática de reportes
        # if from_number in report_sessions and report_sessions[from_number]["images"]:
        #     system_prompt += "\n\nINSTRUCCIÓN IMPORTANTE: NO crees ningún reporte ni menciones folios en tu respuesta. El usuario debe decir EXPLÍCITAMENTE 'Crear reporte' para que se genere. No inventes folios ni digas que has creado un reporte a menos que yo te confirme que el reporte ya fue generado."

        llm_service = OpenAIService(
            config=config,
            api_key=os.getenv("OPENAI_API_KEY"),
            system=system_prompt,
            function_manager=function_manager
        )
        
        # Alternative DeepSeek service
        # deepseek_service = DeepSeekService(
        #     config=config,
        #     api_key=os.getenv("DEEPSEEK_API_KEY"),
        #     system=system_prompt,
        #     function_manager=function_manager
        # )

        # Procesar la imagen si está disponible
        if 'image_description' in locals() and image_description:
            image_message = f"[Imagen recibida. Descripción: {image_description}]"
            # No es necesario añadirlo otra vez ya que el cuerpo del mensaje ya contiene esta info
            # conversation_history.add_user_message(image_message)

        # Formatear el historial de mensajes para el modelo.
        # El último mensaje ya es el input actual del usuario y se enviará
        # por separado a generate_response para evitar duplicarlo.
        formatted_history = [
            {"role": "user", "content": message.content} if isinstance(message, HumanMessage)
            else {"role": "system", "content": message.content} if isinstance(message, SystemMessage)
            else {"role": "assistant", "content": message.content}
            for message in conversation_history.messages
        ]

        structured_history = formatted_history[:-1] if formatted_history else []
        llm_service.seed_conversation_history(structured_history)
        logger.debug(
            "Historial estructurado preparado para el modelo: %s mensajes previos",
            len(structured_history),
        )
        log_operational_decision_trace(
            from_number,
            "before_llm_generation",
            body=body[:240],
            reply_context=reply_context,
            history_messages=len(structured_history),
            report_state=build_report_state_snapshot(from_number),
        )
        transfer_guard_context[str(message_id)] = {
            "from_number": from_number,
            "body": body or "",
            "explicit_handoff": is_explicit_human_handoff_request(body or ""),
            "report_intent": detect_report_intent(body or "", ""),
            "report_state": build_report_state_snapshot(from_number),
        }

        fixed_phone_response = resolve_fixed_security_phone_response(body)
        if fixed_phone_response:
            response_content = fixed_phone_response
            logger.critical(
                "📞 [FIXED SECURITY PHONE] Respuesta fija aplicada para %s: %s",
                from_number,
                response_content,
            )
        else:
            # Generar la respuesta del modelo con historial estructurado y el
            # mensaje actual como nuevo input del usuario.
            model_response = llm_service.generate_response(user_input=body)
            response_content = ""
            async for response in model_response:
                response_content += str(response)
            
        # Asegurar que response_content sea un string
        if isinstance(response_content, list):
            response_content = " ".join([str(item) for item in response_content])
        elif not isinstance(response_content, str):
            response_content = str(response_content)

        response_content = normalize_user_facing_response(
            response_content,
            customer_phone=from_number,
        )
        log_operational_decision_trace(
            from_number,
            "after_llm_generation",
            response_preview=response_content[:400],
            should_create_report_session=should_create_report_session(body, response_content),
            report_state=build_report_state_snapshot(from_number),
        )
        transfer_guard_context.pop(str(message_id), None)

        if from_number in report_sessions and assistant_asked_for_optional_image(response_content):
            with report_sessions_lock:
                report_sessions[from_number]["image_prompted"] = True
                report_sessions[from_number]["timestamp"] = datetime.now(pytz.timezone('America/Mexico_City'))
            logger.critical(f"🖼️ [IMAGE PROMPTED] Pregunta de imagen registrada para {from_number}")
        
        # Guardar la respuesta en el historial y en la base de datos
        conversation_history.add_ai_message(response_content)
        assistant_message = Message(
            time=current_datetime,
            senderName="Assistant",
            message=response_content,
            number=from_number,
            uid=uid,
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )

        # ============================================================================
        # 🎯 AUTO-GUARDAR INFORMACIÓN DETECTADA EN LA CONVERSACIÓN
        # ============================================================================
        if from_number and body and (should_create_report_session(body, response_content) or reply_context.get('is_reply', False)):
            logger.critical(f"💾 [AUTO-SAVE] Iniciando detección automática para {from_number} (reply: {reply_context.get('is_reply', False)})")

            # Si es una respuesta, darle mayor prioridad a la detección automática
            if reply_context.get('is_reply', False):
                create_or_update_report_session(from_number)
                
                # Intentar detectar qué tipo de dato es basado en el contexto
                original_message = reply_context.get('original_message', '').lower()
                user_response = body.strip()
                
                # Detección contextual mejorada
                if any(keyword in original_message for keyword in ['número', 'numero']):
                    if user_response.isdigit() and 1 <= int(user_response) <= 99999:
                        save_user_answer(from_number, "selection6", user_response)
                        logger.critical(f"💾 [CONTEXT SAVE] Número guardado por contexto: {user_response}")
                        
                elif any(keyword in original_message for keyword in ['calle', 'dirección', 'direccion']):
                    if len(user_response) > 2:
                        save_user_answer(from_number, "selection5", user_response)
                        logger.critical(f"💾 [CONTEXT SAVE] Calle guardada por contexto: {user_response}")
                        
                elif any(keyword in original_message for keyword in ['colonia', 'col.', 'barrio']):
                    if len(user_response) > 2:
                        save_user_answer(from_number, "selection7", user_response)
                        logger.critical(f"💾 [CONTEXT SAVE] Colonia guardada por contexto: {user_response}")
                        
                elif any(keyword in original_message for keyword in ['problema', 'tipo', 'asunto']):
                    save_user_answer(from_number, "selection4", user_response)
                    logger.critical(f"💾 [CONTEXT SAVE] Problema guardado por contexto: {user_response}")
                        
                elif any(keyword in original_message for keyword in ['nombre', 'como te llamas']):
                    if len(user_response) > 1:
                        save_user_answer(from_number, "selection2", user_response)
                        logger.critical(f"💾 [CONTEXT SAVE] Nombre guardado por contexto: {user_response}")

            create_or_update_report_session(from_number)
            
            # 1. DETECTAR NOMBRE DEL USUARIO
            if sender_name and sender_name != "Usuario" and sender_name.strip():
                save_user_answer(from_number, "selection2", sender_name)
                logger.critical(f"💾 [AUTO-SAVE] Nombre guardado: {sender_name}")
            
            # 2. DETECTAR TIPO DE PROBLEMA - DICCIONARIO COMPLETO
            problem_keywords = {
                # LUMINARIAS Y ALUMBRADO
                "luminaria": "982", "luminarias": "982", "luz": "982", "luces": "982", 
                "foco": "982", "focos": "982", "alumbrado": "981", "lámpara": "982",
                "poste": "1060", "arbotante": "983",
                
                # BACHES Y PAVIMENTO  
                "bache": "984", "baches": "984", "hueco": "984", "huecos": "984",
                "pavimento": "980", "recarpeteo": "980", "asfalto": "980",
                "hundimiento": "1037", "zanja": "1039", "rotura": "1039",
                
                # LIMPIEZA Y BASURA
                "basura": "974", "sucio": "1068", "suciedad": "1068", "escombro": "986",
                "residuos": "974", "desperdicios": "974", "barrido": "348",
                "contenedor": "1069", "lote baldío": "976", "banqueta": "989",
                
                # DRENAJE Y AGUA
                "drenaje": "727", "alcantarilla": "727", "coladera": "224", "tapa": "1065",
                "agua": "1109", "fuga": "726", "inundación": "985", "desazolve": "985",
                "pluvial": "224", "registro": "1061",
                
                # SEMÁFOROS Y TRÁNSITO
                "semáforo": "523", "semáforos": "523", "luz roja": "1073", 
                "sincronización": "1074", "tránsito": "962", "congestionamiento": "963",
                "señalamiento": "900", "vial": "965",
                
                # ÁRBOLES Y ÁREAS VERDES
                "árbol": "979", "árboles": "979", "poda": "979", "rama": "81",
                "tala": "1098", "planta": "1079", "área verde": "1096",
                "parque": "978", "jardín": "1096", "césped": "1096",
                
                # ANIMALES
                "perro": "994", "perros": "994", "gato": "994", "gatos": "994",
                "animal muerto": "16", "mascota": "995", "animal": "14",
                "veterinaria": "995", "esterilización": "995",
                
                # CABLES Y TELECOMUNICACIONES
                "cable": "19", "cables": "19", "cable caído": "19", "fibra": "1170",
                "poste caído": "1060", "cables expuestos": "1064",
                
                # RUIDO Y CONTAMINACIÓN
                "ruido": "1000", "música": "407", "volumen": "407", "fiesta": "953",
                "contaminación": "999", "humo": "998", "polvo": "998", "olor": "750",
                
                # SEGURIDAD Y VIOLENCIA
                "robo": "961", "violencia": "891", "maltrato": "892", "abuso": "892",
                "policía": "955", "vigilancia": "955", "emergencia": "964",
                
                # SERVICIOS PÚBLICOS
                "estacionamiento": "1076", "parquímetro": "624", "mercado": "947",
                "transporte": "1090", "ruta": "1108", "parabús": "1035",
                
                # CONSTRUCCIÓN Y OBRAS
                "construcción": "903", "obra": "932", "banqueta": "774", "cordón": "774",
                "puente": "477", "barandal": "993", "bolardo": "987",
                
                # TRÁMITES Y SERVICIOS
                "licencia": "956", "permiso": "952", "trámite": "912", "pasaporte": "949",
                "registro civil": "1123", "acta": "1123", "INE": "1118", "IMSS": "1119"
            }
            
            body_lower = body.lower()
            response_lower = response_content.lower() if response_content else ""
            combined_text = f"{body_lower} {response_lower}"
            
            # Buscar palabras clave en el texto combinado
            for keyword, code in problem_keywords.items():
                if keyword in combined_text:
                    save_user_answer(from_number, "selection1", code)
                    save_user_answer(from_number, "selection4", f"Problema reportado: {keyword}")
                    logger.critical(f"💾 [AUTO-SAVE] Tipo detectado: '{keyword}' → código {code}")
                    break
            
            # 3. DETECTAR INFORMACIÓN DE UBICACIÓN
            import re
            
            # DETECTAR CALLE
            calle_patterns = [
                r"(?i)(?:en\s+la\s+)?(?:calle|ave|avenida)\s+([a-záéíóúñ\s\d]+?)(?:\s+(?:número|#|\d)|,|$)",
                r"(?i)en\s+([a-záéíóúñ\s]+?)(?:\s+(?:número|#|\d)|,|$)",
                r"(?i)ubicad[oa]?\s+en\s+([a-záéíóúñ\s]+?)(?:\s+(?:número|#|\d)|,|$)"
            ]
            
            for pattern in calle_patterns:
                match = re.search(pattern, combined_text)
                if match:
                    calle = match.group(1).strip()
                    # Filtrar palabras comunes que no son calles
                    excluded_words = ["la", "el", "una", "un", "esta", "está", "esa", "ese", "problema", "reporte"]
                    if len(calle) > 2 and not any(word in calle.lower() for word in excluded_words):
                        save_user_answer(from_number, "selection5", calle)
                        logger.critical(f"💾 [AUTO-SAVE] Calle detectada: {calle}")
                        break
            
            # DETECTAR NÚMERO
            numero_patterns = [
                r"(?i)n[uú]mero\s+(\d+)",
                r"(?i)#\s*(\d+)",
                r"(?i)(?:calle|ave|avenida)\s+[a-záéíóúñ\s]+\s+(\d{1,5})\b"
            ]
            
            for pattern in numero_patterns:
                match = re.search(pattern, combined_text)
                if match:
                    numero = match.group(1)
                    if 1 <= int(numero) <= 99999:  # Validar rango razonable
                        save_user_answer(from_number, "selection6", numero)
                        logger.critical(f"💾 [AUTO-SAVE] Número detectado: {numero}")
                        break
            
            # DETECTAR COLONIA
            colonia_patterns = [
                r"(?i)(?:de\s+la\s+)?colonia\s+([a-záéíóúñ\s]+?)(?:\s|,|$)",
                r"(?i)col\.\s+([a-záéíóúñ\s]+?)(?:\s|,|$)",
                r"(?i)(?:en\s+)?(?:la\s+)?([a-záéíóúñ\s]{4,}?)(?:\s+colonia|$)"
            ]
            
            for pattern in colonia_patterns:
                match = re.search(pattern, combined_text)
                if match:
                    colonia = match.group(1).strip()
                    # Filtrar palabras comunes
                    excluded_words = ["misma", "zona", "área", "lugar", "sitio", "parte", "lado"]
                    if len(colonia) > 3 and not any(word in colonia.lower() for word in excluded_words):
                        save_user_answer(from_number, "selection7", colonia)
                        logger.critical(f"💾 [AUTO-SAVE] Colonia detectada: {colonia}")
                        break
        else:
            logger.critical(f"💾 [SKIP] Conversación normal para {from_number}, no se crea sesión de reporte")


        # 4. USAR DATOS DEL CONTEXTO SI ESTÁN DISPONIBLES
        if 'address' in locals() and address and address != "No he recibido ubicación":
            logger.critical(f"💾 [AUTO-SAVE] Procesando address del contexto: {address}")
            # Separar dirección en componentes
            if ',' in address:
                parts = [part.strip() for part in address.split(',')]
                if len(parts) >= 2:
                    save_user_answer(from_number, "selection5", parts[0])  # Calle
                    save_user_answer(from_number, "selection7", parts[1])  # Colonia
                    logger.critical(f"💾 [AUTO-SAVE] Dirección separada: '{parts[0]}' / '{parts[1]}'")
            else:
                # Si no hay coma, asumir que es solo calle
                save_user_answer(from_number, "selection5", address)
                logger.critical(f"💾 [AUTO-SAVE] Calle del contexto: '{address}'")

        # 5. LOG DE RESUMEN DE DATOS GUARDADOS
        logger.critical(f"💾 [RESUMEN FINAL] Datos guardados para {from_number}:")
        datos_guardados = 0
        for i in range(1, 8):
            saved_value = get_user_answer(from_number, f"selection{i}")
            if saved_value:
                logger.critical(f"💾   selection{i}: '{saved_value}'")
                datos_guardados += 1

        logger.critical(f"💾 [TOTAL] {datos_guardados} campos guardados para {from_number}")

    # ============================================================================
    # FIN DEL CÓDIGO DE AUTO-DETECCIÓN
    # ============================================================================

        logger.debug(f"Guardando respuesta del asistente en BD: {response_content[:30]}...")
        db.Insert(assistant_message)
        await manage_message_history(db, from_number)

    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"Error al generar la respuesta: {str(e)}")
        logger.exception("💥 [LLM FAILURE] type=%s from_number=%s uid=%s", error_type, from_number, uid)
        return JSONResponse(content={"error": f"Error al generar respuesta: {str(e)}"}, status_code=500)
    
    
    # Enviar la respuesta a través de Chat2Desk
    current_time = datetime.now().timestamp()

    # Verificar si ya se envió una respuesta a este número recientemente 
    if from_number in last_response_time:
        time_since_last_response = current_time - last_response_time[from_number]
        # Si han pasado menos de 5 segundos desde la última respuesta, no enviar otra
        if time_since_last_response < 5:  # 5 segundos como tiempo mínimo entre respuestas
            logger.info(f"Evitando respuesta duplicada para {from_number} (solo han pasado {time_since_last_response:.2f} segundos)")
            return JSONResponse(content={"status": True, "message": "Evitada respuesta duplicada"})

    # Actualizar el tiempo de la última respuesta
    last_response_time[from_number] = current_time

    try:
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        # Check if the response contains phrases that could trigger finalization
        blocked_phrases = [
                "ya terminé", "ya termine", "listo", "finalizar reporte", 
                "estoy listo", "he terminado", "terminar", "finalizar",
                "terminé de enviar", "no más imágenes", "cuando hayas terminado",
                "avísame cuando", "solo indícamelo", "indicarme cuando desees"
                        ]

        for phrase in blocked_phrases:
            if phrase.lower() in response_content.lower():
                # Modify the message to avoid triggering phrases
                response_content = response_content.replace(
                    phrase, 
                    f"{phrase[0]}*{phrase[1:]}"  # Add an asterisk to prevent exact matching
                )
                logger.warning(f"Modified trigger phrase in bot response: {phrase}")

        function_call_patterns = [
            "transfer_to_group", 
            "call_sid =",
            "functions.hangup",
            "await save_client_selection",
            "save_client_selection"
        ]
        
        # Check if the response looks like a function call or system instruction
        is_function_call = any(pattern in response_content for pattern in function_call_patterns)

        # If this looks like a function call instruction or system message, replace it
        if is_function_call:
            logger.warning(f"Detected function call in response: {response_content}")
            log_operational_decision_trace(
                from_number,
                "function_call_text_detected",
                response_preview=response_content[:300],
            )
            
            # Detectar texto residual de transfer_to_group del LLM.
            # La transferencia real debe ocurrir por el flujo explícito o vía tool call,
            # no por parseo textual del mensaje.
            if "transfer_to_group" in response_content:
                logger.warning(f"🔄 TEXTO DE TRANSFERENCIA DETECTADO EN RESPUESTA: {response_content[:100]}")

                import re as regex_module
                clean_message = regex_module.sub(r'transfer_to_group\s*\([^)]*\)', "", response_content)
                clean_message = clean_message.replace("transfer_to_group", "")
                clean_message = clean_message.strip()

                if not clean_message or len(clean_message.strip()) < 10:
                    clean_message = "Te voy a conectar con un agente humano que podrá ayudarte mejor. Un momento por favor."

                response_content = clean_message
                logger.critical(f"🧹 MENSAJE LIMPIADO PARA USUARIO (sin ejecutar transferencia textual): {response_content}")
                log_operational_decision_trace(
                    from_number,
                    "transfer_text_sanitized",
                    response_preview=response_content[:300],
                    reason="legacy_textual_transfer_disabled",
                )
            
            # Check if it's a hangup or farewell
            elif any(p in response_content for p in ["functions.hangup", "call_sid ="]):
                response_content = "¡Entendido! Que tengas un excelente día. ¡Hasta pronto!"

            # Generic fallback for other function calls
            else:
                response_content = "Estoy procesando tu solicitud. Dame un momento por favor."

        data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": response_content
        }

        log_chat2desk_outbound_attempt(
            "whatsapp_main",
            data,
            from_number=from_number,
            message_id=message_id,
        )
        # Envío robusto con manejo de errores específicos
        response = requests.post(chat2desk_url, json=data, headers=headers, timeout=30)
        log_chat2desk_outbound_response(
            "whatsapp_main",
            response,
            from_number=from_number,
            message_id=message_id,
        )

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("status") == "success":
                persist_successful_delivery_marker(db, from_number, uid, message_id)
                logger.debug(f"Respuesta enviada exitosamente a Chat2Desk")
                content = {"status": True, "message": "Respuesta enviada por Chat2Desk"}
            else:
                logger.error(f"Error en respuesta Chat2Desk: {response_data}")
                content = {"status": False, "error": "Error en la respuesta de Chat2Desk"}
                
        elif response.status_code == 400:
            # Manejar errores específicos de cliente
            try:
                error_data = response.json()
                errors = error_data.get("errors", {})
                client_errors = errors.get("client_id", [])
                
                # Cliente bloqueado
                if any("blocked" in str(error).lower() for error in client_errors):
                    logger.warning(f"Cliente {from_number} está bloqueado en Chat2Desk")
                    content = {"status": True, "message": "Cliente bloqueado - no se envió mensaje"}
                    
                # Cliente no existe  
                elif any("does not exist" in str(error) for error in client_errors):
                    logger.warning(f"Cliente {from_number} no existe en Chat2Desk")
                    content = {"status": False, "error": "Cliente no existe"}
                else:
                    logger.error(f"Error 400 no manejado: {error_data}")
                    content = {"status": False, "error": f"Error 400: {str(error_data)[:100]}"}
                    
            except json.JSONDecodeError:
                logger.error(f"Error 400 - respuesta no JSON: {response.text}")
                content = {"status": False, "error": "Error 400 - respuesta inválida"}
                
        elif response.status_code == 429:
            logger.warning(f"Rate limit en Chat2Desk para {from_number}")
            content = {"status": False, "error": "Rate limit - reintenta más tarde"}
            
        else:
            logger.error(f"Error HTTP {response.status_code}: {response.text}")
            content = {"status": False, "error": f"Error HTTP {response.status_code}"}
            
    except requests.Timeout:
        logger.error(f"Timeout enviando mensaje a {from_number}")
        content = {"status": False, "error": "Timeout en Chat2Desk"}
        
    except requests.ConnectionError:
        logger.error(f"Error de conexión con Chat2Desk para {from_number}")
        content = {"status": False, "error": "Error de conexión con Chat2Desk"}
        
    except requests.RequestException as e:
        logger.error(f"Error de conexión con Chat2Desk: {str(e)}")
        content = {"status": False, "error": f"Error de conexión: {str(e)}"}
        
    except Exception as e:
        logger.error(f"Error inesperado al enviar mensaje: {str(e)}")
        content = {"status": False, "error": f"Error inesperado: {str(e)}"}

    farewell_keywords = ["gracias", "adiós", "adios", "hasta luego", "chao", "bye", "es todo", "terminar"]
    bot_farewell_indicators = ["que tengas", "hasta luego", "adiós", "adios", "buen día", "hasta pronto"]
    if (any(keyword in body.lower() for keyword in farewell_keywords) and
        any(indicator in response_content.lower() for indicator in bot_farewell_indicators)):
        logger.info(
            "👋 [FAREWELL] Despedida detectada para %s, conservando sesión para evitar cierres prematuros",
            from_number,
        )

    return JSONResponse(content=content)

def format_phone_number(phone):
    """
    Formatea un número de teléfono para usarlo con Chat2Desk.
    
    Args:
        phone (str): Número de teléfono en cualquier formato
        
    Returns:
        str: Número formateado (sin '+' y con prefijo 521 si es de México)
    """
    # Eliminar cualquier caracter no numérico
    phone = ''.join(filter(str.isdigit, phone))
    
    # Asegurarse que tenga el prefijo de México para WhatsApp (521)
    if phone.startswith('52') and len(phone) >= 12:
        # Ya tiene el formato correcto (52 + 1 + 10 dígitos)
        return phone
    elif phone.startswith('52') and len(phone) == 10:
        # Falta el '1' después del código de país
        return f"521{phone[2:]}"
    elif len(phone) == 10:
        # Solo tiene los 10 dígitos, agregar prefijo 521
        return f"521{phone}"
    elif len(phone) == 12 and phone.startswith('52'):
        # Ya tiene formato internacional (52 + 10 dígitos)
        return phone
    
    # Si no coincide con ningún patrón conocido, devolver como está
    return phone

@router.post("/report-status")
async def report_status_update(request: Request):
    """
    Endpoint para recibir actualizaciones de estados de reportes y enviar notificaciones
    por WhatsApp a los clientes correspondientes. Solo se envían notificaciones
    para estados "en progreso" y "concluido".
    """
    try:
        # Obtener los datos del cuerpo de la solicitud
        payload = await request.json()
        logger.debug(f"Payload de actualización de reporte recibido: {payload}")
        
        # Validar campos requeridos
        required_fields = ["reportId", "reportStatus", "phoneNumber"]
        for field in required_fields:
            if field not in payload:
                return JSONResponse(
                    content={"error": f"Campo requerido ausente: {field}"}, 
                    status_code=400
                )
        
        # Extraer datos
        report_id = payload["reportId"]
        report_status = payload["reportStatus"].lower()  # Convertir a minúsculas para comparación
        phone_number = payload["phoneNumber"]
        
        # Solo procesar estados específicos
        if report_status != "en progreso" and report_status != "concluido":
            logger.debug(f"Estado '{report_status}' no requiere notificación. Solo se notifican 'en progreso' y 'concluido'")
            return JSONResponse(content={
                "status": True,
                "message": f"No se requiere notificación para el estado: {report_status}"
            })
        
        # Formatear el número de teléfono para Chat2Desk
        original_phone = phone_number
        phone_number = format_phone_number(phone_number)
        logger.debug(f"Número de teléfono formateado: {original_phone} -> {phone_number}")
            
        # Buscar cliente en Chat2Desk
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_base_url = "https://api.chat2desk.com.mx/v1"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        # Buscar cliente por número de teléfono
        search_url = f"{chat2desk_base_url}/clients"
        params = {"phone": phone_number}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error al buscar cliente en Chat2Desk: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error al buscar cliente: {response.status_code}"}, 
                status_code=500
            )
            
        response_data = response.json()
        logger.debug(f"Respuesta de búsqueda de cliente: {response_data}")
        
        # Verificar si se encontró el cliente basado en la estructura de respuesta de Chat2Desk
        if response_data.get("status") != "success" or not response_data.get("data") or len(response_data.get("data", [])) == 0:
            # Cliente no encontrado, lo creamos
            logger.debug(f"Cliente no encontrado, creando nuevo cliente con número: {phone_number}")
            create_url = f"{chat2desk_base_url}/clients"
            client_data = {
                "phone": phone_number,
                "transport": "wa_direct"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(create_url, json=client_data, headers=headers)
                
            if response.status_code != 200:
                logger.error(f"Error al crear cliente en Chat2Desk: {response.status_code} - {response.text}")
                return JSONResponse(
                    content={"error": f"Error al crear cliente: {response.status_code}"}, 
                    status_code=500
                )
                
            create_response = response.json()
            

            if create_response.get("status") != "success":
                logger.error(f"Error en la respuesta al crear cliente: {create_response}")
                return JSONResponse(
                    content={"error": "Error al crear cliente en Chat2Desk"}, 
                    status_code=500
                )
                
            client_id = create_response.get("data", {}).get("id")
        else:
            # Cliente encontrado
            client_id = response_data.get("data")[0].get("id")
            
        # Obtener información del canal (channel_id)
        if not client_id:
            return JSONResponse(
                content={"error": "No se pudo obtener el ID del cliente"}, 
                status_code=500
            )
            
        # En lugar de consultar los canales, usar un valor fijo
        channel_id = 43906  # Valor fijo conocido para el canal de WhatsApp
        logger.debug(f"Cliente identificado: client_id={client_id}, usando channel_id fijo={channel_id}")
        
        # Preparar y enviar el mensaje al cliente
        message_url = f"{chat2desk_base_url}/messages"
        
        # Construir mensaje según el estado específico del reporte
        if report_status == "en progreso":
            message_text = f"Su reporte #{report_id} ya se encuentra en proceso de atención. Un técnico está trabajando para resolver su solicitud lo antes posible."
        elif report_status == "concluido":
            message_text = f"¡Buenas noticias! Su reporte #{report_id} ha sido concluido satisfactoriamente. Gracias por su paciencia."
        
        # Si hay información adicional en el payload, incluirla en el mensaje
        if "additionalInfo" in payload and payload["additionalInfo"]:
            message_text += f"\n\nInformación adicional: {payload['additionalInfo']}"
            
        message_data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": message_text
        }
        
        # Enviar el mensaje
        async with httpx.AsyncClient() as client:
            response = await client.post(message_url, json=message_data, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error al enviar mensaje: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error al enviar mensaje: {response.status_code}"}, 
                status_code=500
            )
            
        send_response = response.json()
        if send_response.get("status") != "success":
            logger.error(f"Error en la respuesta al enviar mensaje: {send_response}")
            return JSONResponse(
                content={"error": "Error al enviar mensaje en Chat2Desk"}, 
                status_code=500
            )
            
        # Almacenar el mensaje en la base de datos local
        db = LocalStorage()
        message = Message(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            senderName="Sistema",
            message=message_text,
            number=phone_number,
            uid=f"report-{report_id}-{datetime.now().timestamp()}",
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )
        db.Insert(message)
        await manage_message_history(db, phone_number)
        
        logger.debug(f"Mensaje de actualización enviado exitosamente para el reporte #{report_id} - Estado: {report_status}")
        
        return JSONResponse(content={
            "status": True, 
            "message": "Notificación de actualización de reporte enviada",
            "reportId": report_id,
            "clientId": client_id,
            "reportStatus": report_status
        })
        
    except Exception as e:
        logger.error(f"Error al procesar la actualización del reporte: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": f"Error al procesar la solicitud: {str(e)}"}, 
            status_code=500
        )
@router.get("/health")
async def health():
    import psutil, ping3
    ls = LocalStorage()
    configs = ls.GetAll(Config)
    configs = { c.name: c.value for c in configs }

    domains = json.loads(configs.get("PingDomains")) if 'PingDomains' in configs else []
    domains.extend([
        { "name": "AWS", "domain": 'ec2.amazonaws.com'},
        { "name": "Google", "domain": 'google.com'},
        { "name": "Twilio", "domain": "chunderw-gll.twilio.com"}
    ])

    try:
        temperatures = psutil.sensors_temperatures()
        if temperatures:
            temperature = temperatures['coretemp'][0].current
        else:
            temperature = False
    except (AttributeError, KeyError):
        temperature = False
    
    pings = []
    for domain in domains:
        ping = ping3.ping(domain["domain"])
        ping = int(ping * 1000) if ping is not None else False
        pings.append({ "domain": domain["domain"], "ping": ping, "name": domain["name"] })

    metrics = {
        'processor': psutil.cpu_percent(interval=1),
        'memory': psutil.virtual_memory().percent,
        'storage': psutil.disk_usage('/').percent,
        'temperature': temperature,
        'ping': pings
    }
    
    return metrics


# ===============================================
# 🆕 ENDPOINTS ADMINISTRATIVOS ANTI-DUPLICACIÓN
# ===============================================

@router.post("/admin/clear-protection/{phone_number}")
async def clear_protection(phone_number: str):
    """
    Endpoint administrativo para limpiar protecciones de un número específico.
    Usar solo en casos de emergencia cuando un usuario legítimo no puede crear reportes.
    """
    try:
        items_cleared = dedup_manager.force_clear_protection(phone_number)
        
        return {
            "status": "success",
            "message": f"Protecciones eliminadas para {phone_number}",
            "phone": phone_number,
            "items_cleared": items_cleared,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error clearing protection for {phone_number}: {str(e)}")
        return {
            "status": "error", 
            "message": str(e),
            "phone": phone_number
        }

@router.post("/admin/reset-conversation/{phone_number}")
async def reset_conversation(phone_number: str):
    """
    Endpoint administrativo para reiniciar por completo la conversación de un número.
    Limpia historial en BD, sesiones en memoria y protecciones anti-duplicados.
    """
    try:
        deleted_messages = db.delete_messages_by_number(phone_number)
        dedup_items_cleared = dedup_manager.force_clear_protection(phone_number)

        memory_cleanup = {
            "report_sessions": False,
            "user_answers": False,
            "reports_in_progress": False,
            "completed_reports": False,
            "user_sessions": False,
            "recently_completed_reports": False,
            "transferred_numbers": False,
            "last_response_time": False,
            "recently_returned_to_bot": False,
            "closed_by_inactivity": False,
            "hsm_sent_reports": False,
            "sent_evaluation_messages": False,
            "finalized_report_numbers": False,
        }

        with report_sessions_lock:
            if phone_number in report_sessions:
                del report_sessions[phone_number]
                memory_cleanup["report_sessions"] = True

        if phone_number in user_answers:
            del user_answers[phone_number]
            memory_cleanup["user_answers"] = True

        with reports_lock:
            if phone_number in reports_in_progress:
                del reports_in_progress[phone_number]
                memory_cleanup["reports_in_progress"] = True

        if phone_number in completed_reports:
            del completed_reports[phone_number]
            memory_cleanup["completed_reports"] = True

        if phone_number in user_sessions:
            del user_sessions[phone_number]
            memory_cleanup["user_sessions"] = True

        if phone_number in recently_completed_reports:
            del recently_completed_reports[phone_number]
            memory_cleanup["recently_completed_reports"] = True

        if phone_number in transferred_numbers:
            del transferred_numbers[phone_number]
            memory_cleanup["transferred_numbers"] = True

        if phone_number in last_response_time:
            del last_response_time[phone_number]
            memory_cleanup["last_response_time"] = True

        if phone_number in recently_returned_to_bot:
            del recently_returned_to_bot[phone_number]
            memory_cleanup["recently_returned_to_bot"] = True

        if phone_number in closed_by_inactivity:
            del closed_by_inactivity[phone_number]
            memory_cleanup["closed_by_inactivity"] = True

        if phone_number in hsm_sent_reports:
            del hsm_sent_reports[phone_number]
            memory_cleanup["hsm_sent_reports"] = True

        if phone_number in sent_evaluation_messages:
            del sent_evaluation_messages[phone_number]
            memory_cleanup["sent_evaluation_messages"] = True

        if phone_number in finalized_report_numbers:
            finalized_report_numbers.discard(phone_number)
            memory_cleanup["finalized_report_numbers"] = True

        logger.warning(
            f"🧹 [ADMIN RESET] Conversación reiniciada para {phone_number}. "
            f"Mensajes borrados: {deleted_messages}, protecciones: {dedup_items_cleared}, memoria: {memory_cleanup}"
        )

        return {
            "status": "success",
            "message": f"Conversación reiniciada para {phone_number}",
            "phone": phone_number,
            "deleted_messages": deleted_messages,
            "dedup_items_cleared": dedup_items_cleared,
            "memory_cleanup": memory_cleanup,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error resetting conversation for {phone_number}: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "phone": phone_number,
        }

@router.get("/admin/dedup-status")
async def dedup_status():
    """
    Endpoint para ver el estado general del sistema anti-duplicación.
    """
    try:
        general_status = dedup_manager.get_status()
        return {
            "status": "success",
            "data": general_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dedup status: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/admin/dedup-status/{phone_number}")
async def dedup_status_phone(phone_number: str):
    """
    Endpoint para ver el estado específico de un número de teléfono.
    """
    try:
        phone_status = dedup_manager.get_status(phone_number)
        return {
            "status": "success",
            "data": phone_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dedup status for {phone_number}: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "phone": phone_number
        }


@router.get("/admin/operational-audit/latest")
async def operational_audit_latest():
    try:
        report = read_latest_operational_audit_report()
        if not report:
            return JSONResponse(
                content={
                    "status": "not_found",
                    "message": "No hay reporte operativo generado todavía.",
                },
                status_code=404,
            )

        return {
            "status": "success",
            "data": report,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting latest operational audit: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500,
        )


@router.get("/admin/operational-audit/reports")
async def operational_audit_reports(limit: int = 20):
    try:
        safe_limit = max(1, min(limit, 100))
        reports = list_operational_audit_reports(limit=safe_limit)
        return {
            "status": "success",
            "count": len(reports),
            "data": reports,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error listing operational audit reports: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500,
        )


@router.get("/admin/operational-audit/live")
async def operational_audit_live(hours: int = 24):
    try:
        report = generate_operational_audit_snapshot(window_hours=hours)
        return {
            "status": "success",
            "data": report,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error generating live operational audit: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500,
        )
# ---------------------
# Definición de la aplicación FastAPI
# ---------------------
# app = FastAPI(lifespan=lifespan)
# app.include_router(router)
