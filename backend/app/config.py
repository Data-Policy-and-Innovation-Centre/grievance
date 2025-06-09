import os
from pydantic_settings import BaseSettings 
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    JANSUNANI_API_USERNAME: str = os.getenv("JANSUNANI_API_USERNAME")
    JANSUNANI_API_PASSWORD: str = os.getenv("JANSUNANI_API_PASSWORD")

    class Config:
        env_file = ROOT_DIR / ".env"

settings = Settings()



