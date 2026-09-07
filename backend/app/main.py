from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import health_check
from app.api.routes import chat
from app.api.routes import documents

setup_logging()

app = FastAPI(title=settings.app_name)

app.include_router(health_check.router)
app.include_router(chat.router)
app.include_router(documents.router)