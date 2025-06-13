import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.db.models import Base

connect_args = {"check_same_thread": False} if os.getenv("ENV") == "dev" else {}
engine = create_engine(
    settings.DB_URL,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)