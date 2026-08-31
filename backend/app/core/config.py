from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# backend/ -> project root/
ROOT_DIR = BASE_DIR.parent

class Settings(BaseSettings):
    app_name: str = "BIDAR-API"
    log_level: str = "INFO"
    documents_jsonl_path: Path = ROOT_DIR / "ai" / "data" / "processed" / "RFP100_documents_DEV_v0.1.jsonl"
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
