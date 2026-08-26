from fastapi import FastAPI

from app.core.config import settings
from app.api.routes import health_check
from app.api.routes import chat


app = FastAPI(title=settings.app_name)

app.include_router(health_check.router)
app.include_router(chat.router)