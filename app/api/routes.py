import os
import json
import logging
import asyncio
import threading
import traceback
import base64
import requests
import httpx
import pytz
import psycopg2
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Response, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from twilio.twiml.voice_response import VoiceResponse, Connect
from typing import Dict, List, Optional, Any, Union, TypeVar, Generic
from pydantic import BaseModel, Field
























# Import your existing modules
from app.util.database import LocalStorage
from app.models.Config import Config
from app.models.Message import Message
from app.services.llm.openai_service import OpenAIService
from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions
from app.util.logger import logger
from app.services.functions.implementations.geocoding import latlong_to_address
from app.services.functions.implementations.transfer_message_event import transfer_to_group
from app.services.stt.media_transcriber import TranscribeOGG
from langchain_community.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema import HumanMessage, AIMessage, SystemMessage

# Import the multi-agent framework
from agents import (
    Agent, HandoffOutputItem, ItemHelpers, MessageOutputItem, RunContextWrapper,
    Runner, ToolCallItem, ToolCallOutputItem, TResponseInputItem, function_tool,
    handoff, trace,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Constants (from your existing code)
INACTIVITY_THRESHOLD = 2 * 60  # 2 minutes
transfer_timeout = 15 * 60  # 15 minutes

# =======================================
# Agent Context Models
# =======================================

class WhatsAppBaseContext(BaseModel):
    """Base context model shared by all WhatsApp agents"""
    phone_number: str
    customer_name: str = "Usuario"
    chat_id: Optional[str] = None
    client_id: Optional[str] = None
    channel_id: Optional[int] = None
    last_active: datetime = Field(default_factory=lambda: datetime.now(pytz.timezone('America/Mexico_City')))
    
    def update_activity(self):
        self.last_active = datetime.now(pytz.timezone('America/Mexico_City'))

class ReportContext(WhatsAppBaseContext):
    """Context for report creation agent"""
    images: List[str] = Field(default_factory=list)
    image_descriptions: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    report_in_progress: bool = False
    last_image_timestamp: Optional[datetime] = None

class CustomerSupportContext(WhatsAppBaseContext):
    """Context for customer support agent"""
    issue_category: Optional[str] = None
    ticket_id: Optional[str] = None
    
class SwitchboardContext(WhatsAppBaseContext):
    """Context for the triage/switchboard agent"""
    current_agent_name: str = "switchboard"

# Type variable for context
TContext = TypeVar('TContext', bound=WhatsAppBaseContext)

# =======================================
# Global State 
# =======================================

# In-memory store for active conversation contexts
conversation_contexts = {}  # key: phone_number, value: appropriate context object
processed_message_ids = set()  # For deduplication
finalized_report_numbers = set()  # To prevent duplicate report submission
reports_lock = threading.Lock()  # For thread safety
transferred_numbers = {}  # Numbers transferred to human agents

# =======================================
# Function Tools
# =======================================

@function_tool(name_override="analyze_image", description_override="Analyze an image and return a description")
async def analyze_image(context: RunContextWrapper[ReportContext], image_url: str) -> str:
    """
    Analyzes an image using GPT-4 Vision and returns a description.
    Also updates the context with image information.
    """
    try:
        # Download the image
        response = requests.get(image_url)
        image_content = BytesIO(response.content)
        
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Analyze the image
        image_analysis = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe esta imagen en detalle."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64.b64encode(image_content.getvalue()).decode('utf-8')}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
        )
        
        # Get description
        description = image_analysis.choices[0].message.content
        
        # Update context
        context.context.images.append(image_url)
        context.context.image_descriptions.append(description)
        context.context.last_image_timestamp = datetime.now(pytz.timezone('America/Mexico_City'))
        
        return description
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return f"Error al analizar la imagen: {str(e)}"

@function_tool(name_override="process_location", description_override="Process location information from coordinates or text")
async def process_location(context: RunContextWrapper[ReportContext], location_text: str = None, latitude: float = None, longitude: float = None) -> str:
    """
    Processes location information from either coordinates or text description.
    Updates the context with the location information.
    """
    try:
        # If we have coordinates, convert to address
        if latitude is not None and longitude is not None:
            address = await latlong_to_address(latitude, longitude)
            context.context.location = address
            return f"Ubicación registrada: {address}"
        
        # Otherwise use the text description
        elif location_text:
            context.context.location = location_text
            return f"Ubicación registrada: {location_text}"
            
        return "No se pudo procesar la ubicación"
    except Exception as e:
        logger.error(f"Error processing location: {str(e)}")
        return f"Error al procesar la ubicación: {str(e)}"

@function_tool(name_override="finalize_report", description_override="Finalize a report with collected images and location")
async def finalize_report(context: RunContextWrapper[ReportContext]) -> str:
    """
    Finalizes a report with the collected images and location.
    Calls the existing save_client_selection function.
    """
    from app.services.functions.implementations.save_selection import save_client_selection
    
    phone_number = context.context.phone_number
    images = context.context.images
    descriptions = context.context.image_descriptions
    location = context.context.location or "Ubicación no especificada"
    
    # VALIDATION: Check if we have images
    if not images or len(images) == 0:
        return "No hay imágenes para este reporte. Por favor, envíe al menos una imagen."
    
    # VALIDATION: Check if this number has recently finalized a report
    if phone_number in finalized_report_numbers:
        logger.warning(f"Reporte ya finalizado recientemente para {phone_number}, ignorando solicitud duplicada")
        return "Ya has enviado un reporte recientemente. Por favor, espera antes de enviar otro."
    
    # VALIDATION: Check if a report is already in progress
    with reports_lock:
        if context.context.report_in_progress:
            logger.warning(f"Ya hay un reporte en proceso para {phone_number}, ignorando solicitud adicional")
            return "Tu reporte ya está siendo procesado. Por favor, espera unos momentos."
        
        # Mark as in progress
        context.context.report_in_progress = True
    
    try:
        # Create the report
        folio = await save_client_selection(
            phone_number, 
            location,
            "", "", "", "", "", "",
            None,
            images,
            descriptions
        )
        
        # Add to finalized set and schedule removal after 5 minutes
        finalized_report_numbers.add(phone_number)
        asyncio.create_task(remove_from_finalized(phone_number, 300))
        
        # Clear the context for future reports
        context.context.images = []
        context.context.image_descriptions = []
        context.context.location = None
        context.context.report_in_progress = False
        
        return f"Tu reporte ha sido generado con éxito. El número de folio para tu reporte es {folio}."
    except Exception as e:
        logger.error(f"Error al procesar reporte para {phone_number}: {str(e)}")
        # Reset in_progress flag
        context.context.report_in_progress = False
        return f"Error al finalizar el reporte: {str(e)}. Por favor, intenta nuevamente."

@function_tool(name_override="transfer_to_human", description_override="Transfer the conversation to a human agent")
async def transfer_to_human(context: RunContextWrapper[WhatsAppBaseContext], reason: str = None, group_id: int = None) -> str:
    """
    Transfers the conversation to a human agent.
    """
    phone_number = context.context.phone_number
    
    try:
        # Add to transferred numbers with expiration timestamp
        expiration_time = datetime.now().timestamp() + transfer_timeout
        transferred_numbers[phone_number] = expiration_time
        
        # Execute the actual transfer
        result = await transfer_to_group(phone_number, group_id)
        
        # Schedule removal from transferred set after the timeout period
        asyncio.create_task(remove_from_transferred(phone_number, transfer_timeout))
        
        return f"Conversación transferida a un agente humano. Un agente te atenderá en breve."
    except Exception as e:
        logger.error(f"Error executing transfer: {str(e)}")
        # If transfer fails, remove from transferred numbers
        if phone_number in transferred_numbers:
            del transferred_numbers[phone_number]
        return f"Error al transferir: {str(e)}. Por favor, intenta más tarde."

async def remove_from_finalized(number, delay_seconds):
    """Helper function to remove a number from the finalized set after a delay"""
    await asyncio.sleep(delay_seconds)
    if number in finalized_report_numbers:
        finalized_report_numbers.remove(number)
        logger.debug(f"Número {number} removido de la lista de reportes finalizados después de {delay_seconds} segundos")

async def remove_from_transferred(number, delay_seconds):
    """Helper function to remove a number from the transferred set after a delay"""
    await asyncio.sleep(delay_seconds)
    if number in transferred_numbers:
        del transferred_numbers[number]
        logger.debug(f"Bot re-enabled for {number} after {delay_seconds} seconds")

@function_tool(name_override="search_faqs", description_override="Search for answers in the FAQ database")
async def search_faqs(query: str) -> str:
    """
    Simulated FAQ search tool - in production, connect to your knowledge base.
    """
    # Simulated knowledge base
    knowledge_base = {
        "reportes": "Para crear un reporte, envía imágenes del problema y describe la ubicación. Te guiaré en el proceso.",
        "ubicación": "Puedes compartir tu ubicación usando el botón de WhatsApp o describiendo la dirección en texto.",
        "contacto": "Puedes contactar a nuestro equipo de soporte en el teléfono 800-123-4567 o por correo a soporte@ejemplo.com.",
        "horario": "Nuestro horario de atención es de lunes a viernes de 9am a 6pm.",
        "estatus": "Para consultar el estatus de tu reporte, proporciona el número de folio que recibiste."
    }
    
    # Simple keyword-based search
    for keyword, answer in knowledge_base.items():
        if keyword.lower() in query.lower():
            return answer
    
    return "No encontré información específica sobre eso. Para reportes, envía imágenes y ubicación. Para otras consultas, puedo transferirte a un agente."

# =======================================
# Define Agents
# =======================================

# Report creation agent
report_agent = Agent[ReportContext](
    name="Report Agent",
    handoff_description="Especialista en creación de reportes con imágenes y ubicación",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Eres un asistente especializado en la creación de reportes.
    
    Tu objetivo es guiar al usuario a través del proceso de crear un reporte:
    1. Recibir y analizar imágenes relacionadas con el problema (using analyze_image)
    2. Obtener la ubicación del problema (using process_location)
    3. Finalizar el reporte cuando el usuario indique que ha terminado (using finalize_report)
    
    Sé paciente y claro en tus instrucciones. Si el usuario no proporciona suficiente información, 
    pídele claramente lo que necesitas. Si el usuario solicita ayuda con algo que no está relacionado 
    con reportes, considera hacer una transferencia al agente apropiado.
    
    Si el usuario indica que ha terminado (con frases como "listo", "ya terminé", "finalizar reporte"), 
    verifica que tengas al menos una imagen y, si es posible, información de ubicación, antes de finalizar.
    """,
    tools=[analyze_image, process_location, finalize_report]
)

# Customer support agent
support_agent = Agent[CustomerSupportContext](
    name="Customer Support Agent",
    handoff_description="Agente de soporte al cliente para consultas y asistencia general",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Eres un agente de atención al cliente profesional y amable.
    
    Tu objetivo es:
    1. Responder consultas generales de los usuarios
    2. Proporcionar información sobre servicios
    3. Ayudar a resolver problemas sencillos
    4. Transferir conversaciones a agentes humanos cuando sea necesario
    
    Usa la herramienta search_faqs para encontrar respuestas a preguntas comunes.
    
    Si el usuario necesita crear un reporte con imágenes, transfiérelo al Report Agent.
    Si el usuario tiene una consulta muy específica o compleja que requiere asistencia humana,
    usa transfer_to_human.
    """,
    tools=[search_faqs, transfer_to_human]
)

# Switchboard/triage agent
switchboard_agent = Agent[SwitchboardContext](
    name="Switchboard Agent",
    handoff_description="Agente de clasificación inicial que dirige al usuario al especialista adecuado",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    Eres un agente de clasificación inicial. Tu trabajo es entender rápidamente la necesidad del usuario
    y dirigirlo al especialista más adecuado:
    
    1. Si el usuario menciona enviar fotos, imágenes, o reportar un problema → Report Agent
    2. Para consultas generales, información, o asistencia → Customer Support Agent
    
    Mantén tus respuestas breves y eficientes. No intentes resolver el problema tú mismo,
    simplemente identifica qué agente especializado debe atender al usuario.
    
    Si no estás seguro, haz una pregunta de clarificación antes de transferir.
    """,
    handoffs=[
        report_agent,
        support_agent,
    ]
)

# Add handoff paths back to switchboard
report_agent.handoffs.append(switchboard_agent)
support_agent.handoffs.append(switchboard_agent)

# Add handoffs between specialized agents
report_agent.handoffs.append(support_agent)
support_agent.handoffs.append(report_agent)

# =======================================
# Message Processing Functions
# =======================================

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

async def check_inactivity():
    """
    Tarea en background que revisa cada minuto las sesiones activas.
    Si alguna sesión ha estado inactiva más de INACTIVITY_THRESHOLD, se envía un mensaje
    de alerta por Chat2Desk, elimina los mensajes de la base de datos y elimina la sesión.
    """
    while True:
        await asyncio.sleep(60)  # Revisar cada minuto
        now = datetime.now(pytz.timezone('America/Mexico_City'))
        db = LocalStorage()
        
        for number, context in list(conversation_contexts.items()):
            elapsed = (now - context.last_active).total_seconds()
            if elapsed > INACTIVITY_THRESHOLD:
                try:
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
                            channel_id = 43347  # Canal fijo para WhatsApp
                            
                            # Enviar mensaje de desconexión
                            message_data = {
                                "client_id": client_id,
                                "channel_id": channel_id,
                                "transport": "wa_direct",
                                "text": "Se ha desconectado la sesión por inactividad. Para iniciar una nueva conversación, envía un mensaje."
                            }
                            
                            async with httpx.AsyncClient() as client:
                                await client.post(chat2desk_url, json=message_data, headers=headers)
                    
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
                    del conversation_contexts[number]
                    logger.debug(f"Sesión de {number} desconectada por inactividad.")
                except Exception as e:
                    logger.error(f"Error enviando mensaje de desconexión para {number}: {str(e)}")
                    # Aún intentamos eliminar la sesión incluso si falló el envío del mensaje
                    if number in conversation_contexts:
                        del conversation_contexts[number]

async def send_whatsapp_message(client_id, channel_id, message_text):
    """
    Sends a WhatsApp message using Chat2Desk API
    """
    api_token = os.getenv("CHAT2DESK_API_TOKEN")
    chat2desk_url = "https://api.chat2desk.com.mx/v1/messages"
    
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json"
    }
    
    # Check if the message contains function call patterns to sanitize
    function_call_patterns = [
        "transfer_to_group", 
        "call_sid =",
        "functions.hangup",
        "await save_client_selection",
        "save_client_selection"
    ]
    
    # Check if the response looks like a function call or system instruction
    is_function_call = any(pattern in message_text for pattern in function_call_patterns)

    # If this looks like a function call instruction or system message, replace it
    if is_function_call:
        logger.warning(f"Detected function call in response: {message_text}")
        message_text = "Estoy procesando tu solicitud. Dame un momento por favor."

    data = {
        "client_id": client_id,
        "channel_id": channel_id,
        "transport": "wa_direct",
        "text": message_text
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(chat2desk_url, json=data, headers=headers)
    
    if response.status_code != 200:
        logger.error(f"Error al enviar mensaje a Chat2Desk: {response.status_code} - {response.text}")
        return False
    
    return True

# =======================================
# FastAPI Application & Endpoints
# =======================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background tasks
    asyncio.create_task(check_inactivity())
    yield
    # Shutdown: cleanup if needed

app = FastAPI(lifespan=lifespan)
router = APIRouter()

@router.post("/whatsapp")
async def whatsapp(request: Request):
    """
    Endpoint for WhatsApp integration using the multi-agent architecture
    """
    logger.debug("Processing WhatsApp message")
    
    # Database and configuration setup
    db = LocalStorage()
    config = {conf.name: conf.getval() for conf in db.GetAll(Config)}
    
    try:
        # Parse JSON payload
        payload = await request.json()
        logger.debug(f"Received payload: {payload}")
        
        # IMPORTANT: Verify if this is a client message or system response
        message_type = payload.get('type', '')
        uid = payload.get('message_id')
        
        # Only process messages from clients (ignore webhooks from bot messages)
        if message_type != 'from_client':
            logger.debug(f"Ignoring message with type={message_type} (not from_client)")
            return JSONResponse(content={"status": True, "message": "System message ignored"})
        
        # Message deduplication
        if uid in processed_message_ids:
            logger.debug(f"Ignoring duplicate message with id={uid}")
            return JSONResponse(content={"status": True, "message": "Duplicate message ignored"})
        
        # Mark message as processed
        processed_message_ids.add(uid)
        
        # Limit the size of the set to prevent unlimited growth
        if len(processed_message_ids) > 1000:
            processed_message_ids.clear()
            processed_message_ids.add(uid)
        
        # Extract information from Chat2Desk payload
        chat_id = payload.get('chat_id')
        from_number = payload.get('client', {}).get('phone')
        sender_name = payload.get('client', {}).get('name', 'Usuario')
        body = payload.get('text', '')
        channel_id = payload.get('channel_id')
        client_id = payload.get('client_id')
        
        # Check if the number is currently being handled by a human agent
        current_time = datetime.now().timestamp()
        if from_number in transferred_numbers and current_time < transferred_numbers[from_number]:
            # This number has been transferred to a human agent and the transfer hasn't expired
            logger.info(f"Ignoring message from {from_number} as it's being handled by a human agent (expires in {int(transferred_numbers[from_number] - current_time)} seconds)")
            return JSONResponse(content={"status": True, "message": "Message ignored - conversation transferred to human agent"})
        elif from_number in transferred_numbers:
            # Transfer has expired, remove it from the dictionary
            logger.info(f"Transfer for {from_number} has expired, bot is now responding again")
            del transferred_numbers[from_number]
        
        logger.debug(f"Message data: chat_id={chat_id}, sender={sender_name}, message={body}, number={from_number}")
        
        # Process special content types (location, audio, image)
        address = None
        latitude, longitude = None, None
        photo_url = None
        audio_url = None
        image_description = None
        # Handle location data
        if payload.get("coordinates"):
            coords = payload.get("coordinates")
            logger.debug(f"Coordinates format: {coords}")
            
            # Handle comma or space separated coordinates
            if isinstance(coords, str):
                if "," in coords:
                    latitude, longitude = coords.split(",")
                elif " " in coords:
                    longitude, latitude = coords.split(" ")  # In your payload, longitude comes first
                else:
                    logger.error(f"Unknown coordinate format: {coords}")
                    latitude, longitude = None, None
                    
                if latitude and longitude:
                    try:
                        # Ensure coordinates are floats
                        latitude = float(latitude.strip())
                        longitude = float(longitude.strip())
                        
                        # Convert lat/long to address
                        address = await latlong_to_address(latitude, longitude)
                        body = f"Ubicación recibida: {address}\nLatitud: {latitude}, Longitud: {longitude}"
                    except Exception as e:
                        logger.error(f"Error converting coordinates to address: {str(e)}")
                        body = f"Ubicación recibida: Latitud {latitude}, Longitud {longitude}"
                    
                    logger.debug(f"Location message: lat={latitude}, long={longitude}, address={address if 'address' in locals() else 'Not available'}")
        
        # Handle audio data
        elif payload.get("audio"):
            audio_url = payload.get("audio")
            body = TranscribeOGG(audio_url, config["language"])
            logger.debug(f"Transcribed audio: {body}")
        
        # Handle image data
        elif payload.get("photo"):
            photo_url = payload.get("photo")
            if photo_url:
                body = "PHOTO_URL_RECEIVED"  # We'll process this using the analyze_image tool
        
        # Create or get the user context
        if from_number not in conversation_contexts:
            # New conversation - start with the switchboard context
            conversation_contexts[from_number] = SwitchboardContext(
                phone_number=from_number,
                customer_name=sender_name,
                chat_id=chat_id,
                client_id=str(client_id),
                channel_id=channel_id
            )
        else:
            # Update the last active timestamp
            conversation_contexts[from_number].update_activity()
        
        # Get the current context
        current_context = conversation_contexts[from_number]
        
        # Save user message to database
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
        db.Insert(user_message)
        await manage_message_history(db, from_number)
        
        # Load conversation history
        conversation_history = ChatMessageHistory()
        messages_db = db.Search(Message(number=from_number, source="whatsapp"), order='asc', limit=20) or []
        
        for msg in messages_db:
            if msg.direction == "inbound":
                conversation_history.add_user_message(msg.message)
            elif msg.direction == "outbound":
                conversation_history.add_ai_message(msg.message)
        
        # Determine current agent based on context type
        if isinstance(current_context, ReportContext):
            current_agent = report_agent
        elif isinstance(current_context, CustomerSupportContext):
            current_agent = support_agent
        else:  # SwitchboardContext
            current_agent = switchboard_agent
        
        # Prepare input for the agent
        input_items = []
        for message in conversation_history.messages:
            if isinstance(message, HumanMessage):
                input_items.append({"content": message.content, "role": "user"})
            elif isinstance(message, AIMessage):
                input_items.append({"content": message.content, "role": "assistant"})
        
        # Add the current message
        if photo_url:
            # Special handling for images - we'll use the image URL directly
            if isinstance(current_context, ReportContext):
                # For the report agent, mention the photo URL so it can use analyze_image
                input_items.append({"content": f"[He enviado una imagen. URL: {photo_url}]", "role": "user"})
            else:
                # For other agents, add a generic message about sending an image
                input_items.append({"content": "He enviado una imagen", "role": "user"})
        else:
            # Normal text message
            input_items.append({"content": body, "role": "user"})
        
        # Process the message through the agent system
        try:
            with trace(f"WhatsApp conversation", group_id=f"wa-{from_number}"):
                # Run the agent with the appropriate context
                result = await Runner.run(current_agent, input_items, context=current_context)
                
                # Process agent response
                response_text = ""
                new_agent = None
                
                for new_item in result.new_items:
                    if isinstance(new_item, MessageOutputItem):
                        agent_name = new_item.agent.name
                        message_text = ItemHelpers.text_message_output(new_item)
                        response_text += message_text
                        logger.info(f"[{agent_name}] Response: {message_text}")
                    
                    elif isinstance(new_item, HandoffOutputItem):
                        source_agent = new_item.source_agent.name
                        target_agent = new_item.target_agent.name
                        logger.info(f"Handoff from {source_agent} to {target_agent}")
                        
                        # Determine the new context type based on target agent
                        if target_agent == "Report Agent" and not isinstance(current_context, ReportContext):
                            # Create new ReportContext, preserving basic information
                            new_context = ReportContext(
                                phone_number=current_context.phone_number,
                                customer_name=current_context.customer_name,
                                chat_id=current_context.chat_id,
                                client_id=current_context.client_id,
                                channel_id=current_context.channel_id
                            )
                            conversation_contexts[from_number] = new_context
                        
                        elif target_agent == "Customer Support Agent" and not isinstance(current_context, CustomerSupportContext):
                            # Create new CustomerSupportContext
                            new_context = CustomerSupportContext(
                                phone_number=current_context.phone_number,
                                customer_name=current_context.customer_name,
                                chat_id=current_context.chat_id,
                                client_id=current_context.client_id,
                                channel_id=current_context.channel_id
                            )
                            conversation_contexts[from_number] = new_context
                        
                        elif target_agent == "Switchboard Agent" and not isinstance(current_context, SwitchboardContext):
                            # Create new SwitchboardContext
                            new_context = SwitchboardContext(
                                phone_number=current_context.phone_number,
                                customer_name=current_context.customer_name,
                                chat_id=current_context.chat_id,
                                client_id=current_context.client_id,
                                channel_id=current_context.channel_id
                            )
                            conversation_contexts[from_number] = new_context
                
                # Update the current agent for the next message
                conversation_contexts[from_number].current_agent_name = result.last_agent.name
                
                # Save assistant response to database
                if response_text:
                    assistant_message = Message(
                        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        senderName="Assistant",
                        message=response_text,
                        number=from_number,
                        uid=f"resp-{uid}",
                        direction="outbound",
                        mtype="text",
                        source="whatsapp"
                    )
                    db.Insert(assistant_message)
                    await manage_message_history(db, from_number)
                    
                    # Send response via Chat2Desk
                    success = await send_whatsapp_message(
                        client_id=current_context.client_id,
                        channel_id=current_context.channel_id,
                        message_text=response_text
                    )
                    
                    if not success:
                        logger.error(f"Failed to send WhatsApp message to {from_number}")
                
                return JSONResponse(content={"status": True, "message": "Response processed and sent"})
        
        except Exception as e:
            logger.error(f"Error processing message with agent: {str(e)}")
            traceback.print_exc()
            return JSONResponse(content={"error": f"Error processing message: {str(e)}"}, status_code=500)
    
    except KeyError as e:
        logger.error(f"Missing required parameter: {e}")
        return JSONResponse(content={"error": f"Missing parameter {str(e)}"}, status_code=400)
    except Exception as e:
        logger.error(f"Error processing payload: {str(e)}")
        traceback.print_exc()
        return JSONResponse(content={"error": f"Error processing payload: {str(e)}"}, status_code=400)


@router.post("/report-status")
async def report_status_update(request: Request):
    """
    Endpoint to receive report status updates and send WhatsApp notifications
    to corresponding customers. Only sends notifications for "en progreso" and "concluido" states.
    """
    try:
        # Get data from request body
        payload = await request.json()
        logger.debug(f"Report status update payload received: {payload}")
        
        # Validate required fields
        required_fields = ["reportId", "reportStatus", "phoneNumber"]
        for field in required_fields:
            if field not in payload:
                return JSONResponse(
                    content={"error": f"Missing required field: {field}"}, 
                    status_code=400
                )
        
        # Extract data
        report_id = payload["reportId"]
        report_status = payload["reportStatus"].lower()  # Convert to lowercase for comparison
        phone_number = payload["phoneNumber"]
        
        # Only process specific states
        if report_status != "en progreso" and report_status != "concluido":
            logger.debug(f"State '{report_status}' does not require notification. Only 'en progreso' and 'concluido' are notified")
            return JSONResponse(content={
                "status": True,
                "message": f"No notification required for state: {report_status}"
            })
        
        # Format phone number for Chat2Desk
        formatted_phone = phone_number
        # Add phone formatting logic if needed
        
        # Look up client in Chat2Desk
        api_token = os.getenv("CHAT2DESK_API_TOKEN")
        chat2desk_base_url = "https://api.chat2desk.com.mx/v1"
        
        headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        
        # Search for client by phone number
        search_url = f"{chat2desk_base_url}/clients"
        params = {"phone": formatted_phone}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, params=params, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error searching for client in Chat2Desk: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error searching for client: {response.status_code}"}, 
                status_code=500
            )
            
        response_data = response.json()
        
        # Check if client was found based on Chat2Desk response structure
        if response_data.get("status") != "success" or not response_data.get("data") or len(response_data.get("data", [])) == 0:
            # Client not found, create new one
            logger.debug(f"Client not found, creating new client with number: {formatted_phone}")
            create_url = f"{chat2desk_base_url}/clients"
            client_data = {
                "phone": formatted_phone,
                "transport": "wa_direct"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(create_url, json=client_data, headers=headers)
                
            if response.status_code != 200:
                logger.error(f"Error creating client in Chat2Desk: {response.status_code} - {response.text}")
                return JSONResponse(
                    content={"error": f"Error creating client: {response.status_code}"}, 
                    status_code=500
                )
                
            create_response = response.json()
            
            if create_response.get("status") != "success":
                logger.error(f"Error in response when creating client: {create_response}")
                return JSONResponse(
                    content={"error": "Error creating client in Chat2Desk"}, 
                    status_code=500
                )
                
            client_id = create_response.get("data", {}).get("id")
        else:
            # Client found
            client_id = response_data.get("data")[0].get("id")
            
        # Get channel information
        if not client_id:
            return JSONResponse(
                content={"error": "Could not obtain client ID"}, 
                status_code=500
            )
            
        # Use fixed channel value instead of querying channels
        channel_id = 43347  # Fixed known value for WhatsApp channel
        
        # Prepare and send message to client
        message_url = f"{chat2desk_base_url}/messages"
        
        # Build message based on report status
        if report_status == "en progreso":
            message_text = f"Su reporte #{report_id} ya se encuentra en proceso de atención. Un técnico está trabajando para resolver su solicitud lo antes posible."
        elif report_status == "concluido":
            message_text = f"¡Buenas noticias! Su reporte #{report_id} ha sido concluido satisfactoriamente. Gracias por su paciencia."
        
        # Include additional information if available
        if "additionalInfo" in payload and payload["additionalInfo"]:
            message_text += f"\n\nInformación adicional: {payload['additionalInfo']}"
            
        message_data = {
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": "wa_direct",
            "text": message_text
        }
        
        # Send message
        async with httpx.AsyncClient() as client:
            response = await client.post(message_url, json=message_data, headers=headers)
            
        if response.status_code != 200:
            logger.error(f"Error sending message: {response.status_code} - {response.text}")
            return JSONResponse(
                content={"error": f"Error sending message: {response.status_code}"}, 
                status_code=500
            )
            
        send_response = response.json()
        if send_response.get("status") != "success":
            logger.error(f"Error in response when sending message: {send_response}")
            return JSONResponse(
                content={"error": "Error sending message in Chat2Desk"}, 
                status_code=500
            )
            
        # Store message in local database
        db = LocalStorage()
        message = Message(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            senderName="Sistema",
            message=message_text,
            number=formatted_phone,
            uid=f"report-{report_id}-{datetime.now().timestamp()}",
            direction="outbound",
            mtype="text",
            source="whatsapp"
        )
        db.Insert(message)
        await manage_message_history(db, formatted_phone)
        
        logger.debug(f"Update message sent successfully for report #{report_id} - Status: {report_status}")
        
        return JSONResponse(content={
            "status": True, 
            "message": "Report update notification sent",
            "reportId": report_id,
            "clientId": client_id,
            "reportStatus": report_status
        })
        
    except Exception as e:
        logger.error(f"Error processing report update: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": f"Error processing request: {str(e)}"}, 
            status_code=500
        )

@router.get("/health")
async def health():
    """Health check endpoint"""
    import psutil
    
    try:
        # Get CPU, memory and disk usage
        metrics = {
            'processor': psutil.cpu_percent(interval=1),
            'memory': psutil.virtual_memory().percent,
            'storage': psutil.disk_usage('/').percent,
            'agents': {
                'report_agent': {
                    'status': 'active',
                    'conversations': sum(1 for ctx in conversation_contexts.values() if isinstance(ctx, ReportContext))
                },
                'support_agent': {
                    'status': 'active',
                    'conversations': sum(1 for ctx in conversation_contexts.values() if isinstance(ctx, CustomerSupportContext))
                },
                'switchboard_agent': {
                    'status': 'active',
                    'conversations': sum(1 for ctx in conversation_contexts.values() if isinstance(ctx, SwitchboardContext))
                }
            },
            'active_conversations': len(conversation_contexts),
            'transferred_conversations': len(transferred_numbers)
        }
        
        return metrics
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return {"status": "error", "message": str(e)}

# Register router with app
app.include_router(router)