import os
from fastapi import FastAPI
from urllib.parse import quote
from app.util.database import LocalStorage
# from app.util.database import VectorBase
from fastapi.staticfiles import StaticFiles
from app.api.original_routes import router as api_router
from app.frontend.auth import router as auth_router
from app.frontend.routes import router as view_router
import uvicorn


LocalStorage().migrate()
# VectorBase(None)

APP_NAME = "spgg-gpt"

app = FastAPI(title=APP_NAME, version="0.1.0")
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

app.include_router(api_router)
app.include_router(view_router, prefix="/admin")
app.include_router(auth_router, prefix='/auth')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)