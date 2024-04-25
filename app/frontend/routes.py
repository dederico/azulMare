
import os
import json
from fastapi.responses import RedirectResponse
from subprocess import check_output
from fastapi import APIRouter, Request, Response, Depends, Cookie
from app.models.Config import Config
from app.models.User import User
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app.util.database import LocalStorage
from fastapi.security import OAuth2PasswordBearer
from .controllers import Context

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
    if request.cookies.get('beholder') is None:
        return RedirectResponse('/admin/')

    if all([ k not in fragment.lower() for k in ['login', 'signup']]):
        context = { "request": request, "data": Context(fragment).prepare() }
        response = templates.TemplateResponse(f"{fragment}.html", context)
        if fragment == 'logout':
            response.delete_cookie(key='beholder')
        return response
    else:
        return RedirectResponse("/admin/dashboard")