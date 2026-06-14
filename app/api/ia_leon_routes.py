import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.frontend.auth import get_current_colegio_user
from app.models.ColegioMilitarizadoConversation import ColegioMilitarizadoConversation
from app.models.ColegioMilitarizadoUser import ColegioMilitarizadoUser
from app.models.Config import Config
from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions
from app.services.llm.config.system import system_message
from app.services.llm.openai_service import OpenAIService
from app.util.database import LocalStorage


router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str


def _load_config():
    ls = LocalStorage()
    return {conf.name: conf.getval() for conf in ls.GetAll(Config)}


def _build_session_id(user_email: str, requested_session_id: str | None):
    if requested_session_id:
        return requested_session_id
    return f"docente:{user_email}"


def _load_history(session_id: str):
    ls = LocalStorage()
    records = ls.Search(
        ColegioMilitarizadoConversation(session_id=session_id),
        limit=20,
        order="desc",
    )
    if not records:
        return []
    return list(reversed(records))


def _save_message(session_id: str, user_email: str, role: str, content: str):
    LocalStorage().Insert(
        ColegioMilitarizadoConversation(
            session_id=session_id,
            user_email=user_email,
            role=role,
            content=content,
            created_at=datetime.utcnow().isoformat(),
        )
    )


def _format_system_prompt(user: ColegioMilitarizadoUser, session_id: str):
    now = datetime.now()
    display_name = getattr(user, "responsable", None) or user.email
    return system_message.format(
        call_sid=session_id,
        yoga_number=user.email,
        customer_name=display_name,
        address="",
        fotos="",
        date2=now.strftime("%Y-%m-%d"),
        now=now.strftime("%I:%M:%S %p"),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ia_leon(
    payload: ChatRequest,
    current_user: ColegioMilitarizadoUser = Depends(get_current_colegio_user),
):
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    session_id = _build_session_id(current_user.email, payload.session_id)
    config = _load_config()
    service = OpenAIService(
        config=config,
        api_key=os.getenv("OPENAI_API_KEY"),
        function_manager=FunctionManager(registered_functions),
        system=_format_system_prompt(current_user, session_id),
    )

    for history_item in _load_history(session_id):
        service.add_to_conversation(history_item.role, history_item.content)

    answer_chunks = []
    try:
        async for chunk in service.generate_response(message):
            answer_chunks.append(chunk)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo generar la respuesta: {exc}") from exc

    answer = "".join(answer_chunks).strip()
    if not answer:
        answer = "No pude generar una respuesta en este momento."

    _save_message(session_id, current_user.email, "user", message)
    _save_message(session_id, current_user.email, "assistant", answer)

    return ChatResponse(answer=answer, session_id=session_id)
