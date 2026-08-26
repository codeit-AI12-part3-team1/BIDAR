from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    app_name: str = "BIDAR-API"
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
