from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.frontend.routes import router as view_router


app = FastAPI(title="sam-kb-preview", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")
app.include_router(view_router, prefix="/admin")

