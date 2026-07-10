import os
import shutil
from typing import Optional
from sqlalchemy.orm import Session
from storage.postgres_bronze import BronzeDocument

# Define paths relative to the project root
CURATED_DIR = os.path.join("data", "curated")
FAILED_DIR = os.path.join("data", "failed")

os.makedirs(CURATED_DIR, exist_ok=True)
os.makedirs(FAILED_DIR, exist_ok=True)

def evaluate_document(db: Session, document_id: str, file_path: str, text: str, confidence: float, tenant_id: str = None) -> bool:
    """
    Evaluates a document against quality rules.
    Moves the physical file to the appropriate folder.
    Updates the Postgres database with the result.
    
    Returns True if passed, False if failed.
    """
    failure_reason: Optional[str] = None
    
    # Rule 1: Minimum text length
    if len(text.strip()) < 50:
        failure_reason = "insufficient_text_length"
        
    # Rule 2: Minimum OCR Confidence (only applies if confidence is > 0 meaning it was OCR'd)
    elif confidence > 0 and confidence < 60.0:
        failure_reason = "low_ocr_confidence"
        
    # (Future Rules: Required metadata present, exact duplicate logic, etc. would go here)
    
    # Process Result
    filename = os.path.basename(file_path)
    
    if tenant_id:
        doc_record = db.query(BronzeDocument).filter(
            BronzeDocument.document_id == document_id,
            BronzeDocument.tenant_id == tenant_id
        ).first()
    else:
        doc_record = db.query(BronzeDocument).filter(BronzeDocument.document_id == document_id).first()
    
    if failure_reason:
        # Move to failed
        if tenant_id:
            failed_tenant_dir = os.path.join(FAILED_DIR, tenant_id)
            os.makedirs(failed_tenant_dir, exist_ok=True)
            target_path = os.path.join(failed_tenant_dir, filename)
        else:
            target_path = os.path.join(FAILED_DIR, filename)
        
        if doc_record:
            doc_record.status = "failed"
            # No failure_reason column in BronzeDocument yet
            db.commit()
            
        print(f"[QUALITY GATE] REJECTED {filename}: {failure_reason}")
        
    else:
        # Move to curated
        if tenant_id:
            curated_tenant_dir = os.path.join(CURATED_DIR, tenant_id)
            os.makedirs(curated_tenant_dir, exist_ok=True)
            target_path = os.path.join(curated_tenant_dir, filename)
        else:
            target_path = os.path.join(CURATED_DIR, filename)
        
        if doc_record:
            doc_record.status = "curated"
            db.commit()
            
        print(f"[QUALITY GATE] ACCEPTED {filename}")
        
    # Move the actual file
    if os.path.exists(file_path):
        try:
            shutil.copy2(file_path, target_path)
        except Exception as e:
            print(f"[ERROR] Failed to copy {file_path} to {target_path}: {e}")
            
    return failure_reason is None

