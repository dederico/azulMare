import os
import json
from fastapi import FastAPI
from app.models.User import User
from .controllers import Context, create_knowledge_function, create_outgoing_campaign, list_outgoing_campaigns, send_outgoing_campaign
from app.util.logger import logger
from subprocess import check_output
from app.models.Config import Config
from app.models.File import File
from app.util.database import LocalStorage
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import APIRouter, Request, Response, Depends, Cookie
from urllib.parse import quote_plus

router = APIRouter()
templates = Jinja2Templates(directory="app/frontend/pages")
oauth2 = OAuth2PasswordBearer(tokenUrl="token")
PRIMARY_ADMIN_USERNAME = "colegio_militarizado"
PRIMARY_ADMIN_PASSWORD = "leon_2026"
LEGACY_ADMIN_USERNAME = "atencion_ciudadana"
LEGACY_ADMIN_PASSWORD = "sam_2026"
PRIMARY_ADMIN_COOKIE = "colegio_militarizado_admin_auth"
LEGACY_ADMIN_COOKIE = "sam_kb_auth"
ADMIN_COOKIE_VALUE = "ok"

def parse(body):
    payload = {}
    for argument in body.decode().split("&"):
        label, value = argument.strip().split("=")
        payload[label] = value
    return payload

def page(name):
    return f"app/frontend/pages/{name}"


def admin_is_authenticated(request: Request) -> bool:
    return (
        request.cookies.get(PRIMARY_ADMIN_COOKIE) == ADMIN_COOKIE_VALUE
        or request.cookies.get(LEGACY_ADMIN_COOKIE) == ADMIN_COOKIE_VALUE
    )


def render_knowledge_admin_page(request: Request, authenticated: bool, error: str = "", success: str = "", form_data: dict | None = None):
    return templates.TemplateResponse(
        request,
        "sam_base_conocimiento.html",
        {
            "authenticated": authenticated,
            "error": error,
            "success": success,
            "form_data": form_data or {},
        },
    )


def render_outgoing_messages_page(
    request: Request,
    authenticated: bool,
    error: str = "",
    success: str = "",
    form_data: dict | None = None,
):
    campaigns = list_outgoing_campaigns(LocalStorage()) if authenticated else []
    return templates.TemplateResponse(
        request,
        "outgoing_messages.html",
        {
            "authenticated": authenticated,
            "error": error,
            "success": success,
            "form_data": form_data or {},
            "campaigns": campaigns,
        },
    )

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not request.cookies.get('beholder'):
        ls = LocalStorage()
        config = { c.name: c.value for c in ls.GetAll(Config) }
        fragment = "login.html" if "language" in config else "signup.html"
        with open(page(fragment), "r") as file:
            content = file.read()
        return content
    else:
        return RedirectResponse("/admin/dashboard")


@router.get("/colegio-militarizado/base-de-conocimiento", response_class=HTMLResponse)
@router.get("/ciac/sam-base-de-conocimiento", response_class=HTMLResponse)
async def knowledge_admin(request: Request):
    return render_knowledge_admin_page(
        request=request,
        authenticated=admin_is_authenticated(request),
        error=request.query_params.get("error", ""),
        success=request.query_params.get("success", ""),
    )


@router.post("/colegio-militarizado/base-de-conocimiento", response_class=HTMLResponse)
@router.post("/ciac/sam-base-de-conocimiento", response_class=HTMLResponse)
async def knowledge_admin_submit(request: Request):
    form = await request.form()
    payload = {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
    action = payload.get("action", "").strip().lower()
    authenticated = admin_is_authenticated(request)

    if action == "login":
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        valid_credentials = (
            (username == PRIMARY_ADMIN_USERNAME and password == PRIMARY_ADMIN_PASSWORD)
            or (username == LEGACY_ADMIN_USERNAME and password == LEGACY_ADMIN_PASSWORD)
        )
        if valid_credentials:
            response = RedirectResponse(
                url="/admin/colegio-militarizado/base-de-conocimiento?success=" + quote_plus("Acceso concedido."),
                status_code=303,
            )
            response.set_cookie(PRIMARY_ADMIN_COOKIE, ADMIN_COOKIE_VALUE, httponly=True, samesite="lax")
            return response
        return render_knowledge_admin_page(
            request=request,
            authenticated=False,
            error="Credenciales inválidas.",
            form_data={"username": username},
        )

    if action == "logout":
        response = RedirectResponse(url="/admin/colegio-militarizado/base-de-conocimiento", status_code=303)
        response.delete_cookie(PRIMARY_ADMIN_COOKIE)
        response.delete_cookie(LEGACY_ADMIN_COOKIE)
        return response

    if not authenticated:
        return render_knowledge_admin_page(
            request=request,
            authenticated=False,
            error="Tu sesión expiró. Inicia sesión de nuevo.",
        )

    if action == "create":
        try:
            result = create_knowledge_function(LocalStorage(), payload)
            return render_knowledge_admin_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error creating knowledge function: %s", e)
            return render_knowledge_admin_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    return render_knowledge_admin_page(
        request=request,
        authenticated=authenticated,
        error="Acción no soportada.",
        form_data=payload,
    )


@router.get("/colegio-militarizado/mensajes-institucionales", response_class=HTMLResponse)
@router.get("/ciac/mensajes-proactivos", response_class=HTMLResponse)
async def outgoing_messages(request: Request):
    return render_outgoing_messages_page(
        request=request,
        authenticated=admin_is_authenticated(request),
        error=request.query_params.get("error", ""),
        success=request.query_params.get("success", ""),
    )


@router.post("/colegio-militarizado/mensajes-institucionales", response_class=HTMLResponse)
@router.post("/ciac/mensajes-proactivos", response_class=HTMLResponse)
async def outgoing_messages_submit(request: Request):
    form = await request.form()
    payload = {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
    action = payload.get("action", "").strip().lower()
    authenticated = admin_is_authenticated(request)

    if action == "login":
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        valid_credentials = (
            (username == PRIMARY_ADMIN_USERNAME and password == PRIMARY_ADMIN_PASSWORD)
            or (username == LEGACY_ADMIN_USERNAME and password == LEGACY_ADMIN_PASSWORD)
        )
        if valid_credentials:
            response = RedirectResponse(
                url="/admin/colegio-militarizado/mensajes-institucionales?success=" + quote_plus("Acceso concedido."),
                status_code=303,
            )
            response.set_cookie(PRIMARY_ADMIN_COOKIE, ADMIN_COOKIE_VALUE, httponly=True, samesite="lax")
            return response
        return render_outgoing_messages_page(
            request=request,
            authenticated=False,
            error="Credenciales inválidas.",
            form_data={"username": username},
        )

    if action == "logout":
        response = RedirectResponse(url="/admin/colegio-militarizado/mensajes-institucionales", status_code=303)
        response.delete_cookie(PRIMARY_ADMIN_COOKIE)
        response.delete_cookie(LEGACY_ADMIN_COOKIE)
        return response

    if not authenticated:
        return render_outgoing_messages_page(
            request=request,
            authenticated=False,
            error="Tu sesión expiró. Inicia sesión de nuevo.",
        )

    if action == "create":
        try:
            result = create_outgoing_campaign(LocalStorage(), payload)
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error creating outgoing campaign: %s", e)
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    if action == "send_now":
        campaign_id = (payload.get("campaign_id") or "").strip()
        if not campaign_id.isdigit():
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error="No se recibió un identificador de campaña válido.",
                form_data=payload,
            )
        try:
            result = send_outgoing_campaign(LocalStorage(), int(campaign_id))
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error sending outgoing campaign: %s", e)
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    return render_outgoing_messages_page(
        request=request,
        authenticated=authenticated,
        error="Acción no soportada.",
        form_data=payload,
    )

@router.get("/{fragment}", response_class=HTMLResponse)
async def dashboard(request: Request, fragment):
    try:
        if request.cookies.get('beholder') is None:
            #TODO Need to check here if token is valid
            return RedirectResponse('/admin/')
    
        if not os.path.exists(f"app/frontend/pages/{fragment}.html") and not request.query_params.get("json"):
            fragment = "404"

        if all([ k not in fragment.lower() for k in ['login', 'signup']]):
            context = { "request": request, "data": Context(fragment, request.method).prepare(**request.query_params) }
            if not request.query_params.get("json"):
                response = templates.TemplateResponse(f"{fragment}.html", context)
                if fragment == 'logout':
                    response.delete_cookie(key='beholder')
                return response
            return JSONResponse(context["data"])
        else:
            return RedirectResponse("/admin/dashboard")
    except Exception as e:
        logger.error(e)
        context = { "request": request, "data": {} }
        return templates.TemplateResponse(f"500.html", context)
@router.api_route("/{fragment}/{id}", methods=["GET", "POST", "DELETE"], response_class=HTMLResponse)
async def dashboard(request: Request, fragment : str, id : str):
    try:
        if request.cookies.get('beholder') is None:
            #TODO Need to check here if token is valid
            return RedirectResponse('/admin/')
    
        if not os.path.exists(f"app/frontend/pages/subpages/{fragment}.html") and not request.query_params.get("json"):
            fragment = "404"

        if all([ k not in fragment.lower() for k in ['login', 'signup']]):
            payload = await request.form()

            if payload and 'file' in payload:
                data = await payload["file"].read()
                if len(data) > 0:
                    db = LocalStorage()
                    ftype = "contacts" if fragment == 'settings' else 'kb'
                    db.Insert(File(name=payload["file"].filename, data=data, ftype=ftype))
                    logger.info("File '{}' upload completed Successfully!".format(payload["file"].filename))

            payload = {k: v for k, v in payload.items() } if payload else None
            context = { "request": request, "data": Context(fragment, request.method, payload).prepare(id=id, **request.query_params) }

            if not request.query_params.get("json"):
                return templates.TemplateResponse(f"subpages/{fragment}.html", context)

            return JSONResponse(context["data"])
        else:
            return RedirectResponse("/admin/dashboard")
    except Exception as e:
        logger.error(e)
        context = { "request": request, "data": {} }
        return templates.TemplateResponse(f"500.html", context)
