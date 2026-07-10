import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint('file_hash', 'tenant_id', name='uq_documents_file_hash_tenant'),
    )
    
    document_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    file_hash = Column(String, index=True, nullable=False)
    status = Column(String, default="pending", nullable=False)
    failure_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tenant_id = Column(String, nullable=False)
    filename = Column(String, nullable=True)

class BronzeDocument(Base):
    __tablename__ = "bronze_documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, index=True, nullable=False)
    file_hash = Column(String, index=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String, default="pending", nullable=False)
    source_type = Column(String, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    page_count = Column(Integer, nullable=True)
    document_purpose = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tenant_id = Column(String, nullable=False)
    filename = Column(String, nullable=True)
