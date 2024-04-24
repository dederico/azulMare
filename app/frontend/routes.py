
import os
import json
import bcrypt
import base64
import binascii
from fastapi.responses import RedirectResponse
from subprocess import check_output
from fastapi import APIRouter, Request, Depends
from app.models.Config import Config
from app.models.User import User
from fastapi.responses import HTMLResponse
from app.util.database import LocalStorage
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_salt():
    salt = check_output("hostname").decode().strip()
    return "$2a$12$" + base64.b64encode(binascii.a2b_hex(("0" * 32 + salt)[-32:]))

def encrypt_password(password):
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), get_salt())
    return hashed_password

def check_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)

def parse(body):
    payload = {}
    for argument in body.decode().split("&"):
        label, value = argument.strip().split("=")
        payload[label] = value
    return payload

def page(name):
    return f"app/frontend/pages/{name}"

@router.get("/", response_class=HTMLResponse)
async def index():
    ls = LocalStorage()
    config = { c.name: c.value for c in ls.GetAll(Config) }
    fragment = "login.html" if "Lang" in config else "signup.html"
    with open(page(fragment), "r") as file:
        content = file.read()
    return content

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(token: str = Depends(oauth2_scheme)):
    with open(page("dashboard.html"), "r") as file:
        content = file.read()
    return content
