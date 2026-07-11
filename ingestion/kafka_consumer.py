import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import logging
import tempfile
import shutil
from kafka import KafkaConsumer
from sqlalchemy.orm import Session
from storage.postgres_bronze import SessionLocal, BronzeDocument
from extraction.text_extraction import classify_pdf, extract_text_native
from extraction.ocr.extract import extract_text_ocr
from ingestion.classifier import classify_document_purpose
from storage import s3_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC_NAME = "raw_documents"

def run_consumer():
    consumer = KafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=[KAFKA_BROKER],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='ingestion-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )
    
    logger.info(f"Listening to Kafka topic: {TOPIC_NAME}")
    
    db = SessionLocal()
    
    for message in consumer:
        data = message.value
        doc_id = data.get("document_id")
        filename = data.get("filename", "")
        file_hash = data.get("hash")
        file_type = data.get("file_type")
        tenant_id = data.get("tenant_id")
        
        logger.info(f"Received message for doc_id={doc_id} with tenant_id={tenant_id}")
        
        # Verify the document still exists in the Ingestion DB (documents table)
        from ingestion.idempotency import SessionLocal as IngestSession, Document
        db_ingest = IngestSession()
        exists = db_ingest.query(Document).filter(
            Document.document_id == doc_id,
            Document.tenant_id == tenant_id
        ).first()
        db_ingest.close()
        if not exists:
            logger.warning(f"Document {doc_id} for tenant {tenant_id} not found in Ingestion DB. Skipping.")
            continue
        
        s3_key = data.get("s3_key")
        if not s3_key:
            logger.warning(f"No s3_key provided for {doc_id}. Skipping.")
            continue
            
        # Download from S3 to temporary file
        ext = os.path.splitext(filename)[1] if filename else ""
        fd, raw_path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        
        success = s3_client.download_file(s3_key, raw_path)
        if not success:
            logger.error(f"Failed to download {s3_key} from S3. Skipping.")
            if os.path.exists(raw_path):
                os.remove(raw_path)
            continue
            
        logger.info(f"DEBUG_CONSUMER: Downloaded {s3_key} to temp file {raw_path}")
        
        # Determine source_type
        source_type = "unknown"
        if filename.lower().endswith(".csv") or file_type == "text/csv":
            source_type = "csv"
        elif filename.lower().endswith(".pdf"):
            if os.path.exists(raw_path):
                source_type = classify_pdf(raw_path)
            else:
                logger.warning(f"File not found on disk: {raw_path}")
                source_type = "text_pdf" # fallback
        elif filename.lower().endswith((".png", ".jpg", ".jpeg")):
            source_type = "scanned_pdf" # Treats images same as scanned PDFs
        elif filename.lower().endswith(".txt"):
            source_type = "text_native"

        # --- DB-02 Fix: Extract metrics at ingestion time so V1 records are non-NULL ---
        ocr_confidence = None
        page_count = None

        try:
            if source_type in ("text_native", "text_pdf") and os.path.exists(raw_path):
                result = extract_text_native(raw_path)
                page_count = len(result) if result else 0
                # Native PDFs have no OCR confidence — leave as None (by design)
            elif source_type in ("scanned_pdf", "scanned") and os.path.exists(raw_path):
                result = extract_text_ocr(raw_path)
                ocr_confidence = result.get("average_confidence", None)
                page_count = result.get("page_count", None)
        except Exception as e:
            logger.warning(f"Metric extraction failed for {doc_id}: {e}. Metrics will be NULL.")

        # Insert to Bronze
        existing = db.query(BronzeDocument).filter(
            BronzeDocument.document_id == doc_id,
            BronzeDocument.tenant_id == tenant_id
        ).first()
        if not existing:
            new_doc = BronzeDocument(
                document_id=doc_id,
                file_hash=file_hash,
                source_type=source_type,
                status="pending",
                ocr_confidence=ocr_confidence,  # DB-02 Fix: persist at V1
                page_count=page_count,           # DB-02 Fix: persist at V1
                document_purpose=None,           # Will be updated inline
                tenant_id=tenant_id,
                filename=filename
            )
            db.add(new_doc)
            db.commit()
            db.refresh(new_doc)
            logger.info(f"Inserted into bronze_documents: {doc_id} | source_type={source_type} | ocr_confidence={ocr_confidence} | page_count={page_count}")
            
            # --- Inline Real-time Pipeline Processing ---
            logger.info(f"Processing document {doc_id} inline...")
            
            # 1. Read / Extract text content
            text_content = ""
            try:
                if source_type in ("text_native", "text_pdf"):
                    text_content_list = extract_text_native(raw_path)
                    text_content = "\n".join([c["content"] for c in text_content_list])
                elif source_type in ("scanned_pdf", "scanned", "image"):
                    result = extract_text_ocr(raw_path)
                    text_content = result.get("text", "")
                elif source_type in ("txt", "notes"):
                    with open(raw_path, "r", encoding="utf-8") as f:
                        text_content = f.read()
                elif source_type == "csv":
                    with open(raw_path, "r", encoding="utf-8-sig") as f:
                        text_content = f.read()
            except Exception as extract_err:
                logger.error(f"Failed to extract text content inline: {extract_err}")
                
            new_doc.extracted_text = text_content
            
            # 1b. Classify document purpose
            doc_purpose = classify_document_purpose(text_content)
            new_doc.document_purpose = doc_purpose
            logger.info(f"Classified document purpose: {doc_purpose}")
            
            # 2. Evaluate document quality rules (moves file, updates db status)
            try:
                from quality.quality_gate import evaluate_document
                passed = evaluate_document(db, doc_id, s3_key, text_content, ocr_confidence or 0.0, tenant_id=tenant_id)
                db.commit()
                logger.info(f"Quality Gate evaluate complete. Passed: {passed} | Status: {new_doc.status}")
            except Exception as qg_err:
                logger.error(f"Quality Gate evaluate failed: {qg_err}")
                new_doc.status = "failed"
                db.commit()
                
            # 3. Vector Embed document chunks (Only if curated)
            if new_doc.status == "curated":
                try:
                    logger.info(f"Generating Qdrant embeddings for {doc_id} inline...")
                    import rag.embed as embed_module
                    embed_module.main()
                    logger.info(f"Embeddings generated successfully.")
                except Exception as embed_err:
                    logger.error(f"Vector embedding failed: {embed_err}")
            
            # 4. Compile gold layers via dbt compile run
            try:
                logger.info(f"Compiling gold layers via dbt run...")
                dbt_bin = os.path.join(".venv", "Scripts", "dbt.exe") if os.name == "nt" else os.path.join(".venv", "bin", "dbt")
                if not os.path.exists(dbt_bin):
                    dbt_bin = "dbt"
                
                import subprocess
                subprocess.run(
                    [dbt_bin, "run", "--project-dir", "warehouse", "--profiles-dir", "warehouse"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info("dbt run successful.")
            except Exception as dbt_err:
                logger.error(f"dbt run failed: {dbt_err}")
        else:
            logger.info(f"Document {doc_id} already exists in Bronze.")
            
        if 'raw_path' in locals() and os.path.exists(raw_path):
            try:
                os.remove(raw_path)
                logger.info(f"Cleaned up temp file {raw_path}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up temp file {raw_path}: {cleanup_err}")

if __name__ == "__main__":
    run_consumer()

