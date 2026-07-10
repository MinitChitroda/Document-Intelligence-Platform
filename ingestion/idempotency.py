import os
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from storage.postgres_models import Base, Document

# Use 127.0.0.1 by default for local testing to avoid IPv6 (::1) auth issues
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:55432/document_platform")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def compute_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

