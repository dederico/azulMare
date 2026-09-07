import os
import httpx
from app.util.database import LocalStorage
from app.models.Config import Config
from app.models.Message import Message
from datetime import datetime
import pytz
from app.util.logger import logger
import re
from threading import Lock

# Obtener token de API de Chat2Desk
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")
CHAT2DESK_BASE_URL = "https://api.chat2desk.com.mx/v1"
DEFAULT_OPERATOR_GROUP_ID = int(os.environ.get("CHAT2DESK_OPERATOR_GROUP_ID", "1817"))
ROUND_ROBIN_LOCK = Lock()
ROUND_ROBIN_INDEX = 0


def _parse_group_ids(raw_value):
    group_ids = []
    for token in str(raw_value or "").split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        try:
            group_id = int(float(cleaned))
        except (TypeError, ValueError):
            logger.warning("ID de grupo inválido ignorado en configuración: %s", cleaned)
            continue
        if group_id not in group_ids:
            group_ids.append(group_id)
    return group_ids


def _get_configured_operator_group_ids():
    configured_group_ids = []

    try:
        local_storage = LocalStorage()
        config_list = local_storage.Search(Config(name="chat2desk_operator_group_ids"), single=True, json=False)
        if config_list and getattr(config_list, "value", None):
            configured_group_ids = _parse_group_ids(config_list.value)

        if not configured_group_ids:
            config_single = local_storage.Search(Config(name="chat2desk_operator_group_id"), single=True, json=False)
            if config_single and getattr(config_single, "value", None):
                configured_group_ids = _parse_group_ids(config_single.value)
    except Exception as e:
        logger.warning("No se pudo leer configuración de grupos de operadores desde BD: %s", e)

    if not configured_group_ids:
        configured_group_ids = _parse_group_ids(os.environ.get("CHAT2DESK_OPERATOR_GROUP_IDS"))

    if not configured_group_ids:
        configured_group_ids = [DEFAULT_OPERATOR_GROUP_ID]

    return configured_group_ids


def resolve_operator_group_id(preferred_group_id=None):
    configured_group_ids = _get_configured_operator_group_ids()

    if preferred_group_id is not None:
        try:
            normalized_preferred = int(float(preferred_group_id))
        except (TypeError, ValueError):
            logger.warning("preferred_group_id inválido: %s", preferred_group_id)
        else:
            if normalized_preferred in configured_group_ids:
                return normalized_preferred, configured_group_ids, "preferred"
            logger.warning(
                "preferred_group_id=%s no está en grupos configurados=%s; se aplicará round-robin.",
                normalized_preferred,
                configured_group_ids,
            )

    if len(configured_group_ids) == 1:
        return configured_group_ids[0], configured_group_ids, "single"

    global ROUND_ROBIN_INDEX
    with ROUND_ROBIN_LOCK:
        selected_group_id = configured_group_ids[ROUND_ROBIN_INDEX % len(configured_group_ids)]
        ROUND_ROBIN_INDEX += 1

    return selected_group_id, configured_group_ids, "round_robin"

def format_phone_number(phone):
    """
    Formatea un número de teléfono para usarlo con Chat2Desk.
    """
    # Eliminar cualquier caracter no numérico
    phone = ''.join(filter(str.isdigit, phone))
    
    # Asegurarse que tenga el prefijo de México para WhatsApp (521)
    if phone.startswith('52') and len(phone) >= 12:
        return phone
    elif phone.startswith('52') and len(phone) == 10:
        return f"521{phone[2:]}"
    elif len(phone) == 10:
        return f"521{phone}"
    elif len(phone) == 12 and phone.startswith('52'):
        return phone
    
    # Si no coincide con ningún patrón conocido, devolver como está
    return phone

async def transfer_to_group(message_id, group_id=None, reason=None):
    """
    Transfiere una conversación usando el message_id del payload.
    VERSIÓN SÚPER SIMPLE: Usa directamente el message_id del webhook.

    message_id (integer): ID del mensaje del payload. OBLIGATORIO.
    group_id (number): ID del grupo de operadores. Se normaliza al grupo configurado del bot.
    reason (string): Razón de la transferencia (para logs).

    Returns:
        string: Mensaje de confirmación o error.
    """
    try:
        requested_group_id = group_id
        normalized_requested_group_id = None

        if group_id is not None:
            try:
                normalized_requested_group_id = int(float(group_id))
                requested_group_id = normalized_requested_group_id
            except (ValueError, TypeError):
                logger.warning(
                    "group_id no válido: %s, usando configuración dinámica de grupos",
                    group_id,
                )
                requested_group_id = None

        group_id, configured_group_ids, selection_mode = resolve_operator_group_id(normalized_requested_group_id)

        # Configurar encabezados
        api_token = os.environ.get("CHAT2DESK_API_TOKEN")
        if not api_token:
            error_msg = "No se encontró el token de API en las variables de entorno."
            logger.error(error_msg)
            return error_msg
            
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        # ✅ SÚPER SIMPLE: Usar directamente el message_id del payload
        transfer_url = f"{CHAT2DESK_BASE_URL}/messages/{message_id}/transfer_to_group"
        transfer_params = {"group_id": group_id}
        
        logger.debug(f"Transfiriendo mensaje {message_id} al grupo {group_id}")
        logger.debug(f"URL: {transfer_url}")
        logger.debug(f"Params: {transfer_params}")
        logger.critical(
            "🔀 [TRANSFER TRACE] message_id=%s requested_group_id=%s effective_group_id=%s selection_mode=%s configured_group_ids=%s reason=%s",
            message_id,
            requested_group_id,
            group_id,
            selection_mode,
            configured_group_ids,
            reason,
        )

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            transfer_response = await client.get(transfer_url, params=transfer_params, headers=headers)

        response_preview = transfer_response.text[:1000]
        logger.critical(
            "🔀 [TRANSFER API RESPONSE] message_id=%s group_id=%s status_code=%s body=%s",
            message_id,
            group_id,
            transfer_response.status_code,
            response_preview,
        )

        if transfer_response.status_code != 200:
            error_msg = f"Error al transferir mensaje: {transfer_response.status_code} - {transfer_response.text}"
            logger.error(error_msg)
            return error_msg

        try:
            transfer_payload = transfer_response.json()
        except ValueError:
            transfer_payload = None

        if isinstance(transfer_payload, dict) and transfer_payload.get("status") not in (None, "success"):
            error_msg = f"Error al transferir mensaje: 200 - {transfer_response.text}"
            logger.error(error_msg)
            return error_msg
        
        logger.critical(f"✅ TRANSFERENCIA EXITOSA: Mensaje {message_id} transferido al grupo {group_id}")
        
        # Mensaje de éxito
        success_msg = f"La conversación ha sido transferida exitosamente al grupo {group_id}."
        logger.info(success_msg)
        return success_msg
    
    except Exception as e:
        error_msg = f"Error al transferir conversación: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def get_operator_groups():
    """Obtiene la lista de grupos de operadores disponibles."""
    try:
        headers = {
            "Authorization": CHAT2DESK_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        groups_url = f"{CHAT2DESK_BASE_URL}/operators_groups"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(groups_url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Error al obtener grupos: {response.status_code} - {response.text}")
            return []
        
        response_data = response.json()
        
        if response_data.get("status") != "success":
            logger.error("Error en la respuesta de Chat2Desk")
            return []
        
        groups = []
        for group in response_data.get("data", []):
            groups.append({
                "id": group.get("id"),
                "name": group.get("name"),
                "operators_count": len(group.get("operator_ids", [])),
                "operator_ids": group.get("operator_ids", [])
            })
        
        return groups
        
    except Exception as e:
        logger.error(f"Error al obtener grupos de operadores: {str(e)}")
        return []
