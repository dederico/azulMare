import os
from fastapi import FastAPI
from urllib.parse import quote
from app.util.helpers import isAPIEnabled
from app.util.database import LocalStorage
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import app as endpoints
from app.api.routes import router as api_router
from app.frontend.auth import router as auth_router
from app.frontend.routes import router as view_router

LocalStorage().migrate()

APP_NAME = "Beholder"

app = FastAPI(title=APP_NAME, version="0.1.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

if isAPIEnabled():
    app.mount("/api", endpoints)

app.include_router(api_router)
app.include_router(view_router, prefix="/admin")
app.include_router(auth_router, prefix='/auth')