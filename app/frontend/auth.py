from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
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
async def signup(user: UserInLogin):
    ls = LocalStorage()
    users = ls.GetAll(User)
    if len(users) > 0:
        raise HTTPException(status_code=400, detail="Cannot register more then one Admins")
    hashed_password = pwd_context.hash(user.password)
    user = User(username=user.username, password=hashed_password)
    user = ls.Insert(user)

    return {"message": "User created successfully"}

@router.post("/login/")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    ls = LocalStorage()
    users = ls.GetAll(User)
    user = authenticate_user(users, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.id}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}