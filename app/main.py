import os
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from urllib.parse import quote
from app.util.database import LocalStorage
from app.util.logger import logger
# from app.util.database import VectorBase
from fastapi.staticfiles import StaticFiles
from app.frontend.routes import router as view_router
from app.frontend.controllers import process_due_outgoing_campaigns
import uvicorn
from app.services.monitoring.operational_audit import operational_audit_scheduler


logger.info("[BOOT] Import de app.main iniciado")

skip_migrate = os.environ.get("SKIP_LOCAL_MIGRATE", "").strip().lower() in {"1", "true", "yes", "on"}
if skip_migrate:
    logger.warning("[BOOT] SKIP_LOCAL_MIGRATE activo. Se omitirá LocalStorage().migrate()")
else:
    logger.info("[BOOT] Iniciando LocalStorage().migrate()")
    LocalStorage().migrate()
    logger.info("[BOOT] LocalStorage().migrate() terminado")

# VectorBase(None)

APP_NAME = "spgg-gpt"
from app.api.original_routes import router as api_router, lifespan as base_lifespan
from app.frontend.auth import router as auth_router

@asynccontextmanager
async def app_lifespan(app_instance: FastAPI):
    disable_scheduler = os.environ.get("DISABLE_OUTGOING_SCHEDULER", "").strip().lower() in {"1", "true", "yes", "on"}
    disable_operational_audit = os.environ.get("DISABLE_OPERATIONAL_AUDIT", "").strip().lower() in {"1", "true", "yes", "on"}
    scheduler_task = None
    audit_task = None
    async with base_lifespan(app_instance):
        if disable_scheduler:
            logger.warning("[SCHEDULER] DISABLE_OUTGOING_SCHEDULER activo. No se iniciará el scheduler.")
        else:
            scheduler_task = asyncio.create_task(outgoing_campaign_scheduler())
            app_instance.state.outgoing_campaign_scheduler_task = scheduler_task

        if disable_operational_audit:
            logger.warning("[AUDIT] DISABLE_OPERATIONAL_AUDIT activo. No se iniciara el auditor operativo.")
        else:
            audit_task = asyncio.create_task(operational_audit_scheduler())
            app_instance.state.operational_audit_task = audit_task
        try:
            yield
        finally:
            if scheduler_task:
                scheduler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler_task
                logger.info("[SCHEDULER] Scheduler de campañas salientes cancelado")
            if audit_task:
                audit_task.cancel()
                with suppress(asyncio.CancelledError):
                    await audit_task
                logger.info("[AUDIT] Scheduler operativo cancelado")

logger.info("[BOOT] Creando instancia FastAPI")
app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=app_lifespan)
logger.info("[BOOT] Montando archivos estáticos")
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

logger.info("[BOOT] Registrando api_router")
app.include_router(api_router)
logger.info("[BOOT] Registrando view_router con prefijo /admin")
app.include_router(view_router, prefix="/admin")
logger.info("[BOOT] Registrando auth_router con prefijo /auth")
app.include_router(auth_router, prefix='/auth')
logger.info("[BOOT] app.main cargado correctamente")


async def outgoing_campaign_scheduler():
    logger.info("[SCHEDULER] Scheduler de campañas salientes iniciado")
    while True:
        try:
            local_storage = LocalStorage()
            processed = process_due_outgoing_campaigns(local_storage)
            if processed:
                logger.info("[SCHEDULER] Campañas programadas procesadas: %s", processed)
        except Exception as e:
            logger.error("[SCHEDULER] Error procesando campañas programadas: %s", e)
        await asyncio.sleep(30)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
