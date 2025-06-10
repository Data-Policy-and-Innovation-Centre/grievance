import os
from pydantic_settings import BaseSettings
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    JANASUNANI_API_BASE_URL: str = os.getenv(
        "JANASUNANI_API_BASE_URL", "https://janasunani.odisha.gov.in/api/DataServices"
    )
    JANASUNANI_API_USERNAME: str = os.getenv("JANASUNANI_API_USERNAME")
    JANASUNANI_API_PASSWORD: str = os.getenv("JANASUNANI_API_PASSWORD")

    class Config:
        env_file = ROOT_DIR / ".env"


settings = Settings()
