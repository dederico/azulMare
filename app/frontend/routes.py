
import os
import json
from fastapi import FastAPI
from app.models.User import User
from .controllers import Context
from app.util.logger import logger
from subprocess import check_output
from app.models.Config import Config
from app.util.database import LocalStorage
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi import APIRouter, Request, Response, Depends, Cookie

router = APIRouter()
templates = Jinja2Templates(directory="app/frontend/pages")
oauth2 = OAuth2PasswordBearer(tokenUrl="token")

def parse(body):
    payload = {}
    for argument in body.decode().split("&"):
        label, value = argument.strip().split("=")
        payload[label] = value
    return payload

def page(name):
    return f"app/frontend/pages/{name}"

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not request.cookies.get('beholder'):
        ls = LocalStorage()
        config = { c.name: c.value for c in ls.GetAll(Config) }
        fragment = "login.html" if "Lang" in config else "signup.html"
        with open(page(fragment), "r") as file:
            content = file.read()
        return content
    else:
        return RedirectResponse("/admin/dashboard")

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
                with open(f'uploads/{payload["file"].filename}', "wb") as f:
                    f.write(await payload["file"].read())
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