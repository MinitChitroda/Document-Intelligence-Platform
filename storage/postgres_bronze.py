import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from storage.postgres_models import Base, BronzeDocument

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:55432/document_platform")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

