import jwt
import os
from app.models.Config import Config
from passlib.context import CryptContext
from datetime import datetime, timedelta
from app.util.database import LocalStorage
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, HTTPException, Depends, Form
from app.models.User import User, Token, UserInDB, UserInLogin
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

SECRET_KEY = os.environ["SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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

@router.post("/signup/")
#async def signup(language: str = Form(...), username: str = Form(...), password: str = Form(...)):
async def signup(language: str = "es-US", username: str = Form(...), password: str = Form(...)):
    ls = LocalStorage()
    if len(ls.GetAll(User)) == 0:
        hashed_password = pwd_context.hash(password)
        user = ls.Insert(User(username=username, password=hashed_password))
        if hasattr(user, 'id'):
            ls.Insert(Config(name="language", value=language))
            ls.Insert(Config(name="power", value=False))

    return RedirectResponse("/admin/", status_code=302)

@router.post("/login/")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    ls = LocalStorage()
    users = ls.GetAll(User)
    user = authenticate_user(users, form_data.username, form_data.password)
    if not user:
        return RedirectResponse('/admin?msg=invalid%20Username%20or%20Password', status_code=302)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.id}, expires_delta=access_token_expires)
    
    response = RedirectResponse("/admin/dashboard", status_code=302)
    response.set_cookie('beholder', access_token)
    return response