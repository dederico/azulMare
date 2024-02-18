from fastapi import FastAPI
from app.api.routes import router as api_router

# from app.util.setup_config import PrometheusMiddleware, setting_otlp, metrics
import logging
import os


APP_NAME = "call-gpt"
# OTLP_GRPC_ENDPOINT = os.environ.get("OTLP_GRPC_ENDPOINT", "http://tempo:4317")

app = FastAPI(title=APP_NAME, version="0.1.0")

# app.add_middleware(PrometheusMiddleware, app_name=APP_NAME)
# app.add_route("/metrics", metrics)
app.include_router(api_router)

# setting_otlp(app, APP_NAME, OTLP_GRPC_ENDPOINT)


# class EndpointFilter(logging.Filter):
#     # Uvicorn endpoint access log filter
#     def filter(self, record: logging.LogRecord) -> bool:
#         return record.getMessage().find("GET /metrics") == -1


# # Filter out /endpoint
logging.getLogger("uvicorn.access")