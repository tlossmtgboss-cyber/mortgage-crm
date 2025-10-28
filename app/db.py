from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Robust import handling for Base model
try:
    from app.models import Base
except ImportError:
    # Fallback for different directory structures
    from models import Base

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")  # Overwrite with Railway Postgres!
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
