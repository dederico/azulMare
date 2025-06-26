import os
import httpx
from app.util.database import LocalStorage
from app.models.Message import Message
from datetime import datetime
import pytz
from app.util.logger import logger
import re

# Obtener token de API de Chat2Desk
CHAT2DESK_API_TOKEN = os.environ.get("CHAT2DESK_API_TOKEN")
CHAT2DESK_BASE_URL = "https://api.chat2desk.com.mx/v1"

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
    group_id (number): ID del grupo de operadores. Por defecto 1772 (Envios).
    reason (string): Razón de la transferencia (para logs).

    Returns:
        string: Mensaje de confirmación o error.
    """
    try:
        # Usar el valor por defecto si no se proporciona group_id
        if group_id is None:
            group_id = 1772  # ID del grupo Envios por defecto
        else:
            # Asegurar que group_id sea un entero
            try:
                group_id = int(float(group_id))
            except (ValueError, TypeError):
                logger.warning(f"group_id no válido: {group_id}, usando valor por defecto 1772")
                group_id = 1772

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

        async with httpx.AsyncClient() as client:
            transfer_response = await client.get(transfer_url, params=transfer_params, headers=headers)
            
        if transfer_response.status_code != 200:
            error_msg = f"Error al transferir mensaje: {transfer_response.status_code} - {transfer_response.text}"
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