import jwt
import os
from app.models.Config import Config
from app.models.ColegioMilitarizadoUser import ColegioMilitarizadoUser
from passlib.context import CryptContext
from datetime import datetime, timedelta
from app.util.database import LocalStorage
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, HTTPException, Depends, Form
from app.models.User import User, Token, UserInDB, UserInLogin
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

SECRET_KEY = os.environ["SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
colegio_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
http_bearer = HTTPBearer(auto_error=False)


class ColegioLoginRequest(BaseModel):
    email: str
    password: str


class ColegioChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ColegioUserResponse(BaseModel):
    email: str
    name: str
    role: str
    campus: str
    area: str


class ColegioLoginResponse(BaseModel):
    token: str
    must_change_password: bool
    user: ColegioUserResponse

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def verify_colegio_password(plain_password, hashed_password):
    return colegio_pwd_context.verify(plain_password, hashed_password)


def hash_colegio_password(password: str):
    return colegio_pwd_context.hash(password)

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


def get_colegio_user_by_email(email: str):
    ls = LocalStorage()
    user = ls.Search(ColegioMilitarizadoUser(email=email.strip().lower()), single=True)
    if not user or not getattr(user, "is_active", False):
        return None
    return user


def build_colegio_user_response(user):
    return ColegioUserResponse(
        email=user.email,
        name=(getattr(user, "responsable", None) or user.email),
        role=(getattr(user, "role", None) or "staff"),
        campus=(getattr(user, "campus", None) or "General"),
        area=(getattr(user, "area", None) or ""),
    )


def create_colegio_access_token(user):
    expires = timedelta(hours=12)
    return create_access_token(
        data={"sub": user.email, "scope": "colegio_militarizado"},
        expires_delta=expires,
    )


def decode_colegio_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido") from exc

    if payload.get("scope") != "colegio_militarizado":
        raise HTTPException(status_code=401, detail="Token inválido para este recurso")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = get_colegio_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no autorizado")
    return user


async def get_current_colegio_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authorization Bearer requerida")
    return decode_colegio_token(credentials.credentials)

@router.post("/signup/")
async def signup(language: str = Form(...), username: str = Form(...), password: str = Form(...)):
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


@router.post("/login", response_model=ColegioLoginResponse)
async def colegio_login(payload: ColegioLoginRequest):
    user = get_colegio_user_by_email(payload.email)
    if not user or not verify_colegio_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    user.last_login_at = datetime.utcnow().isoformat()
    user.updated_at = user.last_login_at
    LocalStorage().Update(user)

    return ColegioLoginResponse(
        token=create_colegio_access_token(user),
        must_change_password=bool(getattr(user, "must_change_password", False)),
        user=build_colegio_user_response(user),
    )


@router.post("/change-password")
async def colegio_change_password(
    payload: ColegioChangePasswordRequest,
    current_user: ColegioMilitarizadoUser = Depends(get_current_colegio_user),
):
    if not verify_colegio_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")

    current_user.password_hash = hash_colegio_password(payload.new_password)
    current_user.must_change_password = False
    current_user.updated_at = datetime.utcnow().isoformat()
    LocalStorage().Update(current_user)

    return {"ok": True}
