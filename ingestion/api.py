from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, Header, HTTPException, Query
from sqlalchemy.orm import Session
from ingestion.idempotency import get_db, compute_hash, Document, init_db
from ingestion.kafka_producer import publish_raw_document
from rag.query_router import route_query
from rag.retrieval_v2 import preload_model
import mimetypes

import os
import logging

app = FastAPI(title="Ingestion API")

@app.on_event("startup")
def on_startup():
    # In a production app, we would use Alembic for migrations,
    # but for this prototype we'll create the tables on startup.
    init_db()
    os.makedirs(os.path.join("data", "raw"), exist_ok=True)
    preload_model()

@app.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    x_tenant_id: str = Header(None)
):
    if not x_tenant_id or x_tenant_id.strip() == "":
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is missing or empty")
        
    tenant_id = x_tenant_id.strip()
    content = await file.read()
    file_hash = compute_hash(content)
    
    # Check for existing duplicate document for the specific tenant
    existing_doc = db.query(Document).filter(
        Document.file_hash == file_hash,
        Document.tenant_id == tenant_id
    ).first()
    if existing_doc:
        return {"status": "skipped_duplicate", "document_id": existing_doc.document_id}
        
    # Get extension
    ext = ""
    if file.filename:
        _, ext = os.path.splitext(file.filename)
    
    # Save the physical file (inside a tenant-specific folder)
    tenant_dir = os.path.join("data", "raw", tenant_id)
    os.makedirs(tenant_dir, exist_ok=True)
    target_path = os.path.join(tenant_dir, f"{tenant_id}_{file_hash}{ext}")
    logging.info(f"DEBUG_API: target_path resolved to: {os.path.abspath(target_path)}")
    with open(target_path, "wb") as f:
        f.write(content)
        
    # If new, insert into database
    new_doc = Document(file_hash=file_hash, status="pending", tenant_id=tenant_id, filename=file.filename)
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    
    # Detect file type and publish to Kafka in the background
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    background_tasks.add_task(
        publish_raw_document,
        document_id=new_doc.document_id,
        filename=file.filename or "unknown",
        file_hash=f"{tenant_id}_{file_hash}", # Use the unique file name hash to avoid extraction collisions
        file_type=content_type,
        tenant_id=tenant_id
    )
    
    return {"status": "accepted", "document_id": new_doc.document_id}

@app.post("/query")
async def query_documents(
    query: str = Query(...),
    tenant_id: str = Header(..., alias="X-Tenant-ID")
):
    """
    Route query through the v2 pipeline:
      - Tries structured CSV handler first (for all query types)
      - Falls back to semantic retrieval_v2 + generation_v2
    Returns enriched response with routing_path, confidence, query_type, abstained.
    """
    try:
        result = route_query(query=query, tenant_id=tenant_id)

        answer   = result["answer"]
        routing  = result["routing_path"]
        q_type   = result["query_type"]
        conf     = result["confidence"]
        abstain  = result["abstained"]
        citations = result.get("citations", [])

        # chunks: structured path uses chunks_used (int), semantic path has "chunks" list
        chunks_list = result.get("chunks", [])
        if not chunks_list and result.get("structured_used"):
            # Build a synthetic chunk entry from structured result for UI display
            chunks_list = [{
                "chunk_text":       result.get("answer", ""),
                "document_id":      (citations[0]["document_id"] if citations else ""),
                "page_number":      0,
                "source_type":      "csv",
                "chunk_type":       "table",
                "chunk_rank":       1,
                "confidence_score": 1.0,
                "score":            1.0,
            }]

        formatted_citations = [
            {
                "document_id": c.get("document_id"),
                "filename":    c.get("filename"),
                "source_type": c.get("source_type"),
                "page_number": c.get("page_number"),
            }
            for c in citations
        ]

        return {
            "query":                      query,
            "answer":                     answer,
            "routing_path":               routing,
            "query_type":                 q_type,
            "confidence":                 conf,
            "abstained":                  abstain,
            "chunks":                     chunks_list,
            "citations":                  formatted_citations,
            "structured_query_executed":  result.get("structured_query_executed"),
            "low_confidence_warning":     result.get("low_confidence_warning", False),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

