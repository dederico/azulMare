import os
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile
from app.models.User import User
from .controllers import (
    Context,
    APPROVED_HSM_TEMPLATES,
    PROACTIVE_CAMPAIGN_KINDS,
    create_knowledge_function,
    create_outgoing_campaign,
    create_saved_audience_file,
    delete_knowledge_function,
    delete_outgoing_campaign,
    delete_saved_audience_file,
    list_dynamic_knowledge_functions,
    list_outgoing_campaigns,
    list_saved_audience_files,
    send_outgoing_campaign,
)
from app.util.logger import logger
from subprocess import check_output
from app.models.Config import Config
from app.models.File import File
from app.util.database import LocalStorage
from app.services.monitoring.operational_audit import (
    read_latest_operational_audit_report,
    list_operational_audit_reports,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import APIRouter, Request, Response, Depends, Cookie
from urllib.parse import quote_plus

router = APIRouter()
templates = Jinja2Templates(directory="app/frontend/pages")
oauth2 = OAuth2PasswordBearer(tokenUrl="token")
SAM_KB_USERNAME = "atencion_ciudadana"
SAM_KB_PASSWORD = "sam_2026"
SAM_KB_COOKIE = "sam_kb_auth"
SAM_KB_COOKIE_VALUE = "ok"

def parse(body):
    payload = {}
    for argument in body.decode().split("&"):
        label, value = argument.strip().split("=")
        payload[label] = value
    return payload

def page(name):
    return f"app/frontend/pages/{name}"


def sam_kb_is_authenticated(request: Request) -> bool:
    return request.cookies.get(SAM_KB_COOKIE) == SAM_KB_COOKIE_VALUE


def render_sam_kb_page(request: Request, authenticated: bool, error: str = "", success: str = "", form_data: dict | None = None):
    knowledge_functions = list_dynamic_knowledge_functions(LocalStorage()) if authenticated else []
    return templates.TemplateResponse(
        request,
        "sam_base_conocimiento.html",
        {
            "authenticated": authenticated,
            "error": error,
            "success": success,
            "form_data": form_data or {},
            "knowledge_functions": knowledge_functions,
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
    saved_audiences = list_saved_audience_files(LocalStorage()) if authenticated else []
    return templates.TemplateResponse(
        request,
        "outgoing_messages.html",
        {
            "authenticated": authenticated,
            "error": error,
            "success": success,
            "form_data": form_data or {},
            "campaigns": campaigns,
            "saved_audiences": saved_audiences,
            "approved_hsm_templates": APPROVED_HSM_TEMPLATES,
            "campaign_kind_options": PROACTIVE_CAMPAIGN_KINDS,
        },
    )


def render_operational_audit_page(
    request: Request,
    authenticated: bool,
    error: str = "",
    success: str = "",
):
    latest_report = read_latest_operational_audit_report() if authenticated else None
    reports = list_operational_audit_reports(limit=20) if authenticated else []
    return templates.TemplateResponse(
        request,
        "operational_audit.html",
        {
            "authenticated": authenticated,
            "error": error,
            "success": success,
            "latest_report": latest_report,
            "reports": reports,
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


@router.get("/ciac/sam-base-de-conocimiento", response_class=HTMLResponse)
async def sam_base_conocimiento(request: Request):
    return render_sam_kb_page(
        request=request,
        authenticated=sam_kb_is_authenticated(request),
        error=request.query_params.get("error", ""),
        success=request.query_params.get("success", ""),
    )


@router.post("/ciac/sam-base-de-conocimiento", response_class=HTMLResponse)
async def sam_base_conocimiento_submit(request: Request):
    form = await request.form()
    payload = {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
    action = payload.get("action", "").strip().lower()
    authenticated = sam_kb_is_authenticated(request)

    if action == "login":
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if username == SAM_KB_USERNAME and password == SAM_KB_PASSWORD:
            response = RedirectResponse(
                url="/admin/ciac/sam-base-de-conocimiento?success=" + quote_plus("Acceso concedido."),
                status_code=303,
            )
            response.set_cookie(SAM_KB_COOKIE, SAM_KB_COOKIE_VALUE, httponly=True, samesite="lax")
            return response
        return render_sam_kb_page(
            request=request,
            authenticated=False,
            error="Credenciales inválidas.",
            form_data={"username": username},
        )

    if action == "logout":
        response = RedirectResponse(url="/admin/ciac/sam-base-de-conocimiento", status_code=303)
        response.delete_cookie(SAM_KB_COOKIE)
        return response

    if not authenticated:
        return render_sam_kb_page(
            request=request,
            authenticated=False,
            error="Tu sesión expiró. Inicia sesión de nuevo.",
        )

    if action == "create":
        try:
            result = create_knowledge_function(LocalStorage(), payload)
            return render_sam_kb_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error creating knowledge function: %s", e)
            return render_sam_kb_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    if action == "delete":
        try:
            result = delete_knowledge_function(LocalStorage(), payload.get("function_name", ""))
            return render_sam_kb_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error deleting knowledge function: %s", e)
            return render_sam_kb_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    return render_sam_kb_page(
        request=request,
        authenticated=authenticated,
        error="Acción no soportada.",
        form_data=payload,
    )


@router.get("/ciac/mensajes-proactivos", response_class=HTMLResponse)
async def outgoing_messages(request: Request):
    return render_outgoing_messages_page(
        request=request,
        authenticated=sam_kb_is_authenticated(request),
        error=request.query_params.get("error", ""),
        success=request.query_params.get("success", ""),
    )


@router.post("/ciac/mensajes-proactivos", response_class=HTMLResponse)
async def outgoing_messages_submit(request: Request):
    form = await request.form()
    payload = {k: v for k, v in form.items() if isinstance(v, str)}
    action = payload.get("action", "").strip().lower()
    authenticated = sam_kb_is_authenticated(request)

    if action == "login":
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if username == SAM_KB_USERNAME and password == SAM_KB_PASSWORD:
            response = RedirectResponse(
                url="/admin/ciac/mensajes-proactivos?success=" + quote_plus("Acceso concedido."),
                status_code=303,
            )
            response.set_cookie(SAM_KB_COOKIE, SAM_KB_COOKIE_VALUE, httponly=True, samesite="lax")
            return response
        return render_outgoing_messages_page(
            request=request,
            authenticated=False,
            error="Credenciales inválidas.",
            form_data={"username": username},
        )

    if action == "logout":
        response = RedirectResponse(url="/admin/ciac/mensajes-proactivos", status_code=303)
        response.delete_cookie(SAM_KB_COOKIE)
        return response

    if not authenticated:
        return render_outgoing_messages_page(
            request=request,
            authenticated=False,
            error="Tu sesión expiró. Inicia sesión de nuevo.",
        )

    if action == "upload_audience":
        upload = form.get("audience_file")
        audience_label = (payload.get("audience_label") or "").strip()
        drive_url = (payload.get("drive_url") or "").strip()
        if not audience_label:
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error="Debes capturar un nombre para guardar la lista.",
                form_data=payload,
            )
        try:
            file_bytes = b""
            source_name = ""
            source_url = drive_url
            extension = ""
            if isinstance(upload, UploadFile) and upload.filename:
                file_bytes = await upload.read()
                source_name = upload.filename
                extension = Path(upload.filename).suffix.lower()
            elif drive_url:
                import requests

                response = requests.get(drive_url, timeout=60)
                response.raise_for_status()
                file_bytes = response.content
                source_name = drive_url
                extension = Path(drive_url.split("?")[0]).suffix.lower() or ".csv"
            else:
                raise ValueError("Debes subir un archivo .csv/.xlsx o capturar una URL de Drive.")

            result = create_saved_audience_file(
                LocalStorage(),
                audience_label=audience_label,
                file_bytes=file_bytes,
                extension=extension,
                source_name=source_name,
                source_url=source_url,
            )
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error creating saved audience file: %s", e)
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
            )

    if action == "delete_audience":
        audience_file_id = (payload.get("audience_file_id") or "").strip()
        if not audience_file_id.isdigit():
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error="No se recibió un identificador de lista válido.",
                form_data=payload,
            )
        try:
            result = delete_saved_audience_file(LocalStorage(), int(audience_file_id))
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error deleting saved audience file: %s", e)
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error=str(e),
                form_data=payload,
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

    if action == "delete":
        campaign_id = (payload.get("campaign_id") or "").strip()
        if not campaign_id.isdigit():
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                error="No se recibió un identificador de campaña válido.",
                form_data=payload,
            )
        try:
            result = delete_outgoing_campaign(LocalStorage(), int(campaign_id))
            return render_outgoing_messages_page(
                request=request,
                authenticated=True,
                success=result["message"],
                form_data={},
            )
        except Exception as e:
            logger.error("Error deleting outgoing campaign: %s", e)
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


@router.get("/ciac/operational-audit", response_class=HTMLResponse)
async def operational_audit_view(request: Request):
    return render_operational_audit_page(
        request=request,
        authenticated=sam_kb_is_authenticated(request),
        error=request.query_params.get("error", ""),
        success=request.query_params.get("success", ""),
    )


@router.post("/ciac/operational-audit", response_class=HTMLResponse)
async def operational_audit_submit(request: Request):
    form = await request.form()
    payload = {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
    action = payload.get("action", "").strip().lower()

    if action == "login":
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if username == SAM_KB_USERNAME and password == SAM_KB_PASSWORD:
            response = RedirectResponse(
                url="/admin/ciac/operational-audit?success=" + quote_plus("Acceso concedido."),
                status_code=303,
            )
            response.set_cookie(SAM_KB_COOKIE, SAM_KB_COOKIE_VALUE, httponly=True, samesite="lax")
            return response
        return render_operational_audit_page(
            request=request,
            authenticated=False,
            error="Credenciales inválidas.",
        )

    if action == "logout":
        response = RedirectResponse(url="/admin/ciac/operational-audit", status_code=303)
        response.delete_cookie(SAM_KB_COOKIE)
        return response

    return render_operational_audit_page(
        request=request,
        authenticated=sam_kb_is_authenticated(request),
        error="Acción no soportada.",
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
