import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.postgres_bronze import Base, engine, SessionLocal, BronzeDocument
import uuid

def migrate_and_seed():
    print("Dropping existing tables (if any)...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating bronze_documents table...")
    Base.metadata.create_all(bind=engine)
    
    print("Inserting sample rows...")
    db = SessionLocal()
    
    # Doc 1: Perfect digital PDF
    doc1 = BronzeDocument(
        document_id=str(uuid.uuid4()),
        file_hash="hash1_abc",
        version=1,
        status="curated",
        source_type="text_pdf",
        ocr_confidence=None,
        page_count=5,
        tenant_id="tenant_default"
    )
    
    # Doc 2: Scanned PDF
    doc2 = BronzeDocument(
        document_id=str(uuid.uuid4()),
        file_hash="hash2_xyz",
        version=1,
        status="curated",
        source_type="scanned_pdf",
        ocr_confidence=85.5,
        page_count=2,
        tenant_id="tenant_default"
    )
    
    # Doc 3: Failed document
    doc3 = BronzeDocument(
        document_id=str(uuid.uuid4()),
        file_hash="hash3_bad",
        version=1,
        status="failed",
        source_type="scanned_pdf",
        ocr_confidence=42.0,
        page_count=1,
        tenant_id="tenant_default"
    )
    
    db.add_all([doc1, doc2, doc3])
    db.commit()
    
    print("\nQuerying inserted rows:")
    rows = db.query(BronzeDocument).all()
    for r in rows:
        print(f"[{r.id}] DocID: {r.document_id} | Hash: {r.file_hash} | V: {r.version} | Status: {r.status} | Source: {r.source_type} | Conf: {r.ocr_confidence} | Pages: {r.page_count}")
        
    db.close()
    print("\nMigration and verification complete.")

if __name__ == "__main__":
    migrate_and_seed()
