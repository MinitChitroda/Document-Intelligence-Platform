import os
import sys
import subprocess
from sqlalchemy import create_engine, text
import uuid

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.postgres_bronze import BronzeDocument, SessionLocal

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:55432/document_platform")
engine = create_engine(DATABASE_URL)

def print_dim_document(state="BEFORE"):
    print(f"\n--- {state} REPROCESSING: gold.dim_document ---")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT document_id, version, valid_from, valid_to, is_current FROM gold.dim_document WHERE file_hash = 'hash1_abc' ORDER BY version ASC"))
        for row in result:
            print(f"DocID: {row[0][:8]}... | V: {row[1]} | Valid From: {row[2]} | Valid To: {row[3]} | Current: {row[4]}")
    print("-" * 50)

def simulate_reprocessing():
    print_dim_document("BEFORE")
    
    print("\nSimulating Batch Reprocessing...")
    print("Inserting version 2 of 'hash1_abc' into bronze_documents...")
    
    db = SessionLocal()
    # Find original doc1
    doc1 = db.query(BronzeDocument).filter(BronzeDocument.file_hash == "hash1_abc").first()
    
    # Create version 2
    doc1_v2 = BronzeDocument(
        document_id=doc1.document_id, # Same UUID to track history
        file_hash=doc1.file_hash,     # Same file
        version=2,                    # Bump version
        status="curated",
        source_type="text_pdf",
        ocr_confidence=99.9,          # New data from reprocessing
        page_count=5,
        tenant_id=doc1.tenant_id
    )
    db.add(doc1_v2)
    db.commit()
    db.close()
    
    print("Running dbt to update the Data Warehouse...")
    dbt_path = os.path.join(os.path.dirname(sys.executable), "dbt.exe")
    subprocess.run([dbt_path, "run", "--profiles-dir", "."], cwd=r"d:\PYTHON PROJECTS\DATA ENGINEERING PROJECT\warehouse", check=True)
    
    print_dim_document("AFTER")

if __name__ == "__main__":
    simulate_reprocessing()
