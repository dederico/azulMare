import os
from fastapi import FastAPI
from urllib.parse import quote
from app.util.database import LocalStorage
from app.util.database import VectorBase
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.frontend.auth import router as auth_router
from app.frontend.routes import router as view_router

LocalStorage().migrate()
VectorBase(None)

APP_NAME = "call-gpt"

app = FastAPI(title=APP_NAME, version="0.1.0")
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

app.include_router(api_router)
app.include_router(view_router, prefix="/admin")
app.include_router(auth_router, prefix='/auth')