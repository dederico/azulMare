import os
from fastapi import FastAPI
from app.api.routes import router as api_router

APP_NAME = "call-gpt"

app = FastAPI(title=APP_NAME, version="0.1.0")
app.include_router(api_router)