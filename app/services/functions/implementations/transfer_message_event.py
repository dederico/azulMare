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

async def transfer_to_group(phone_number, group_id=None, reason=None, send_notification=True):
    """
    Transfiere una conversación de WhatsApp a un grupo específico de operadores.

    phone_number (string): Número de teléfono del cliente. OBLIGATORIO.
    group_id (number): ID del grupo de operadores. Por defecto 1772 (Envios).
    reason (string): Razón de la transferencia.
    send_notification (boolean): Si es True, envía un mensaje de notificación al usuario.

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
            
        # Formatear número de teléfono
        formatted_phone = format_phone_number(phone_number)
        logger.debug(f"Número de teléfono formateado: {phone_number} -> {formatted_phone}")

        
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
        
        # 1. Buscar el cliente por número de teléfono
        search_url = f"{CHAT2DESK_BASE_URL}/clients"
        params = {"phone_number": formatted_phone}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
            if response.status_code != 200:
                error_msg = f"Error al buscar cliente: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return error_msg
        
        response_data = response.json()
        logger.debug(f"Respuesta de búsqueda de cliente: {response_data}")
        
        # Verificar si se encontró el cliente
        if response_data.get("status") != "success" or not response_data.get("data") or len(response_data.get("data", [])) == 0:
            error_msg = "No se encontró cliente con ese número de teléfono."
            logger.error(error_msg)
            return error_msg
        
        # Buscar el cliente con el número de teléfono exacto que estamos buscando
        client_id = None
        for client in response_data.get("data", []):
            if client.get("phone") == formatted_phone:
                client_id = client.get("id")
                break
        
        # Si no encontramos una coincidencia exacta, usar el primer cliente
        if client_id is None and len(response_data.get("data", [])) > 0:
            client_id = response_data.get("data")[0].get("id")
        
        if client_id is None:
            error_msg = "No se pudo determinar el ID del cliente."
            logger.error(error_msg)
            return error_msg
        
        logger.debug(f"ID del cliente encontrado: {client_id}")
        
        # 2. Obtener información del grupo de operadores
        groups_url = f"{CHAT2DESK_BASE_URL}/operators_groups"
        
        async with httpx.AsyncClient() as client:
            groups_response = await client.get(groups_url, headers=headers)
        
        group_name = "Atención Ciudadana"
        if groups_response.status_code == 200:
            groups_data = groups_response.json()
            for group in groups_data.get("data", []):
                if group.get("id") == group_id:
                    group_name = group.get("name", "Atención Ciudadana")
                    break
        
        # 3. Crear un mensaje nuevo para el cliente - usando valores fijos para channel_id
        message_url = f"{CHAT2DESK_BASE_URL}/messages"

        transfer_message = "Claro, En breve uno de nuestros agentes te atenderá." if send_notification else "..."
        
        # if reason and send_notification:
        #     transfer_message += f"\n\nMotivo: {reason}"

        # Solo enviar el mensaje si send_notification es True
        message_data = {
                "client_id": client_id,
                "channel_id": 43388,  # Valor fijo para channel_id
                "transport": "wa_direct",
                "text": transfer_message
            }
            
        async with httpx.AsyncClient() as client:
            message_response = await client.post(message_url, json=message_data, headers=headers)
            
        if message_response.status_code != 200:
            error_msg = f"Error al enviar mensaje: {message_response.status_code} - {message_response.text}"
            logger.error(error_msg)
            return error_msg
        
        message_result = message_response.json()
        logger.debug(f"Respuesta al enviar mensaje: {message_result}")
                
        # La estructura de la respuesta puede variar, vamos a verificar diferentes posibilidades
        message_id = None

        # Opción 1: data.message_id (según la respuesta que mostraste)
        if message_result.get("data") and isinstance(message_result.get("data"), dict) and "message_id" in message_result.get("data"):
            message_id = message_result.get("data").get("message_id")
        # Opción 2: data.id
        elif message_result.get("data") and isinstance(message_result.get("data"), dict) and "id" in message_result.get("data"):
            message_id = message_result.get("data").get("id")
        # Opción 3: data es directamente un diccionario con id
        elif message_result.get("data") and "id" in message_result:
            message_id = message_result.get("id")
        # Opción 4: id está en el nivel superior
        elif "id" in message_result:
            message_id = message_result.get("id")
        # Opción 5: message_id está en el nivel superior
        elif "message_id" in message_result:
            message_id = message_result.get("message_id")
        # Opción 6: data es una lista y tomamos el primer elemento
        elif message_result.get("data") and isinstance(message_result.get("data"), list) and len(message_result.get("data")) > 0:
            first_item = message_result.get("data")[0]
            if isinstance(first_item, dict):
                if "message_id" in first_item:
                    message_id = first_item.get("message_id")
                elif "id" in first_item:
                    message_id = first_item.get("id")

        if not message_id:
            error_msg = "No se pudo obtener el ID del mensaje enviado."
            logger.error(error_msg)
            logger.error(f"Estructura de respuesta: {message_result}")
            return error_msg
        
        logger.debug(f"ID del mensaje obtenido: {message_id}")
         # 4. Transferir el mensaje al grupo

        transfer_url = f"{CHAT2DESK_BASE_URL}/messages/{message_id}/transfer_to_group"
        transfer_params = {"group_id": group_id}
        logger.debug(f"Intentando transferir mensaje con ID {message_id} a grupo {group_id}. URL: {transfer_url}")

        async with httpx.AsyncClient() as client:
            transfer_response = await client.get(transfer_url, params=transfer_params, headers=headers)
            
        if transfer_response.status_code != 200:
            error_msg = f"Error al transferir mensaje: {transfer_response.status_code} - {transfer_response.text}"
            logger.error(error_msg)
            return error_msg
        
    # ELIMINADO: Ya no enviamos un segundo mensaje de notificación
    
    # 5. Guardar el mensaje en la base de datos local (si se envió un mensaje)
        try:
            db = LocalStorage()
            message = Message(
                time=datetime.now(pytz.timezone('America/Mexico_City')).strftime("%Y-%m-%d %H:%M:%S"),
                senderName="Sistema",
                message=transfer_message,
                number=formatted_phone,
                uid=f"transfer-{client_id}-{datetime.now().timestamp()}",
                direction="outbound",
                mtype="text",
                source="whatsapp"
            )
            db.Insert(message)
        except Exception as db_error:
            logger.error(f"Error al guardar mensaje en la base de datos: {str(db_error)}")
        
        # Mensaje de éxito
        success_msg = f"La conversación ha sido transferida exitosamente al grupo {group_name}."
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