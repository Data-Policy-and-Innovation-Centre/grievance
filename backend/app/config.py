import os
from pydantic_settings import BaseSettings 
from pathlib import Path
from loguru import logger

ROOT_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    DEBUG: bool = ENV != "prod"
    
    class Config:
        env_file = ROOT_DIR / ".env"

settings = Settings()


