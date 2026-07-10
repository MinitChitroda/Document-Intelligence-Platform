import os
from typing import Optional
from sqlalchemy.orm import Session
from storage.postgres_bronze import BronzeDocument
from storage import s3_client

def evaluate_document(db: Session, document_id: str, s3_key: str, text: str, confidence: float, tenant_id: str = None) -> bool:
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
    filename = os.path.basename(s3_key)
    
    if tenant_id:
        doc_record = db.query(BronzeDocument).filter(
            BronzeDocument.document_id == document_id,
            BronzeDocument.tenant_id == tenant_id
        ).first()
    else:
        doc_record = db.query(BronzeDocument).filter(BronzeDocument.document_id == document_id).first()
    
    if failure_reason:
        target_s3_key = s3_key.replace("raw/", "failed/", 1)
        
        if doc_record:
            doc_record.status = "failed"
            # No failure_reason column in BronzeDocument yet
            db.commit()
            
        print(f"[QUALITY GATE] REJECTED {filename}: {failure_reason}")
        
    else:
        target_s3_key = s3_key.replace("raw/", "curated/", 1)
        
        if doc_record:
            doc_record.status = "curated"
            db.commit()
            
        print(f"[QUALITY GATE] ACCEPTED {filename}")
        
    # Move the actual object in S3
    try:
        s3_client.move_object(s3_key, target_s3_key)
    except Exception as e:
        print(f"[ERROR] Failed to move {s3_key} to {target_s3_key} in S3: {e}")
            
    return failure_reason is None

