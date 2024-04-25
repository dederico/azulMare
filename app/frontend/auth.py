from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, HTMLResponse
import jwt
import os
from passlib.context import CryptContext
from datetime import datetime, timedelta
from app.models.Config import Config
from app.models.User import User, Token, UserInDB, UserInLogin
from app.util.database import LocalStorage

SECRET_KEY = os.environ["SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def page(name):
    return f"app/frontend/pages/{name}"

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(users, username: str, password: str):
    if len(users) == 0:
        return False
    user = users.pop()

    if user.username != username:
        return False
    if not verify_password(password, user.password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/signup/", response_class=HTMLResponse)
async def signup(user: UserInLogin):
    ls = LocalStorage()
    users = ls.GetAll(User)
    if len(users) == 0:
        hashed_password = pwd_context.hash(user.password)
        user = User(username=user.username, password=hashed_password)
        user = ls.Insert(user)

    return open(page('login.html'), 'r').read()

@router.post("/login/", response_class=HTMLResponse)
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    ls = LocalStorage()
    users = ls.GetAll(User)
    user = authenticate_user(users, form_data.username, form_data.password)
    if not user:
        return open(page('login.html'), 'r').read()
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.id}, expires_delta=access_token_expires)

    response.set_cookie('beholder', access_token)
    return open(page('dashboard.html'), 'r').read()