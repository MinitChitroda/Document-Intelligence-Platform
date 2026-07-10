"""
rag/embed.py

Embeds all curated document chunks from the Bronze table into Qdrant.

Pipeline:
  1. Query bronze_documents WHERE status = 'curated'
  2. For each document, re-extract text (native PDF chunks / OCR pages)
  3. Embed every chunk with SentenceTransformers all-MiniLM-L6-v2
  4. Upsert into Qdrant collection 'document_chunks'
  5. Verify point count and payload queryability
  6. Print full report and append result to metrics.md

Run from project root:
  $env:PYTHONPATH="."; .venv\Scripts\python rag/embed.py
"""

import os
import sys
import uuid
import logging
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sentence_transformers import SentenceTransformer
from qdrant_client.models import PointStruct

from storage.postgres_bronze import SessionLocal, BronzeDocument
from extraction.text_extraction import extract_text_native, chunk_text
from extraction.ocr.extract import extract_text_ocr
import rag.qdrant_store as qc

logging.basicConfig(level=logging.WARNING)   # suppress verbose ST/Qdrant logs
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
MODEL_NAME   = "all-MiniLM-L6-v2"
METRICS_FILE = os.path.join(os.path.dirname(__file__), "..", "metrics.md")
SEPARATOR    = "=" * 65

# Normalise source_type strings coming out of the Kafka consumer
SOURCE_TYPE_MAP = {
    "text_native": "text_native",
    "text_pdf":    "text_native",
    "scanned":     "scanned_pdf",
    "scanned_pdf": "scanned_pdf",
    "csv":         "csv",
}


def resolve_raw_path(file_hash: str) -> str | None:
    """Find the physical file in data/raw/ by hash prefix."""
    # Check tenant subfolder first
    parts = file_hash.rsplit("_", 1)
    if len(parts) == 2:
        tenant_id = parts[0]
        tenant_dir = os.path.join("data", "raw", tenant_id)
        if os.path.isdir(tenant_dir):
            for fname in os.listdir(tenant_dir):
                if fname.startswith(file_hash):
                    return os.path.join(tenant_dir, fname)

    # Fallback to flat directory
    raw_dir = "data/raw"
    if not os.path.isdir(raw_dir):
        return None
    for fname in os.listdir(raw_dir):
        if fname.startswith(file_hash):
            return os.path.join(raw_dir, fname)
    return None


def extract_chunks(doc: BronzeDocument) -> list[dict]:
    """
    Extract text chunks from a document.
    Returns list of dicts: {page_number, chunk_text}
    """
    raw_path = resolve_raw_path(doc.file_hash)
    if not raw_path:
        print(f"  [WARN] Raw file not found for {doc.document_id[:8]}...")
        return []

    ext = os.path.splitext(raw_path)[1].lower() if raw_path else ""
    if ext in [".png", ".jpg", ".jpeg"]:
        source = "image"
    else:
        source = SOURCE_TYPE_MAP.get(doc.source_type, doc.source_type)

    try:
        if ext == ".csv" or source == "csv":
            import csv
            chunks = []
            with open(raw_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    row_idx = 0
                    for row in reader:
                        row_text = ", ".join([f"{col}: {val}" for col, val in zip(header, row) if val.strip()])
                        if row_text.strip():
                            chunks.append({
                                "page_number": row_idx,
                                "chunk_text": row_text
                            })
                            row_idx += 1
                else:
                    f.seek(0)
                    text = f.read()
                    if text.strip():
                        chunks.append({"page_number": 0, "chunk_text": text})
            return chunks

        elif ext == ".txt":
            chunks = []
            with open(raw_path, "r", encoding="utf-8") as f:
                text = f.read()
            text_chunks = chunk_text(text, chunk_size=400, overlap=50)
            return [
                {"page_number": i, "chunk_text": chunk}
                for i, chunk in enumerate(text_chunks)
                if chunk.strip()
            ]

        elif source == "text_native":
            result = extract_text_native(raw_path)
            return [
                {"page_number": c["chunk_index"], "chunk_text": c["content"]}
                for c in result
                if c["content"].strip()
            ]

        elif source in ["scanned_pdf", "image"]:
            result = extract_text_ocr(raw_path)
            chunks = []
            # Per-page text from OCR
            for page in result.get("pages", []):
                if page["text"].strip():
                    chunks.append({
                        "page_number": page["page_num"] - 1,
                        "chunk_text":  page["text"],
                    })
            # Fallback: use combined text as single chunk if no per-page data
            if not chunks and result.get("text", "").strip():
                chunks.append({"page_number": 0, "chunk_text": result["text"]})
            return chunks

        else:
            return []
    except Exception as e:
        print(f"  [ERROR] Extraction failed for {doc.document_id[:8]}...: {e}")
        return []


def generate_document_summary(extracted_text: str) -> str:
    """Generate a dense statistical and entity-rich summary of the document using Gemini."""
    if not extracted_text or not extracted_text.strip():
        return ""
    
    from rag.gemini_client import get_gemini_manager
    gemini_manager = get_gemini_manager()
    
    prompt = f"""You are a document indexing assistant. Your job is to read the following document content and generate a highly detailed, dense, structured summary specifically designed for downstream search queries, focusing on:
1. High-level statistics (total records, total counts, row counts, averages).
2. Categorical breakdowns (how many items in each category, class, or specialization).
3. Important names, entities, and values.

Keep your response factual, concise, and dense. Rely ONLY on the provided text. Do not invent details.

Text Content:
{extracted_text}
"""
    try:
        # Call Gemini to summarize
        summary = gemini_manager.call_with_fallback(
            messages=[
                {"role": "system", "content": "You are a precise indexing bot that summarizes lists and tables into concise categorical counts and stats."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        return summary.strip()
    except Exception as e:
        print(f"  [WARN] Failed to generate document summary: {e}")
        return ""


def main():
    print(SEPARATOR)
    print("  RAG EMBEDDING — Week 5")
    print(f"  Model : {MODEL_NAME}")
    print(f"  Store : Qdrant  localhost:6333  collection=document_chunks")
    print(SEPARATOR)

    # ── Load model ────────────────────────────────────────────────────────────
    print("\n[1] Loading SentenceTransformer model ...")
    model = SentenceTransformer(MODEL_NAME)
    print(f"    Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")

    # ── Connect to Qdrant ─────────────────────────────────────────────────────
    print("\n[2] Connecting to Qdrant ...")
    client = qc.get_client()
    qc.ensure_collection(client)
    print(f"    Connected. Collection '{qc.COLLECTION_NAME}' ready.")

    # ── Query Bronze for curated docs ─────────────────────────────────────────
    print("\n[3] Querying Bronze table for curated documents ...")
    db = SessionLocal()
    curated_docs = db.query(BronzeDocument).filter(
        BronzeDocument.status == "curated"
    ).all()
    db.close()
    print(f"    Found {len(curated_docs)} curated documents")

    if not curated_docs:
        print("    [WARN] No curated documents found. Run ingestion pipeline first.")
        return

    # ── Extract, embed, upsert ────────────────────────────────────────────────
    print("\n[4] Extracting chunks, embedding, and upserting into Qdrant ...")
    all_points: list[PointStruct] = []
    stats: dict[str, int] = {}

    for doc in curated_docs:
        raw_path = resolve_raw_path(doc.file_hash)
        ext = os.path.splitext(raw_path)[1].lower() if raw_path else ""
        if ext in [".png", ".jpg", ".jpeg"]:
            source = "image"
        else:
            source = SOURCE_TYPE_MAP.get(doc.source_type, doc.source_type)

        chunks = extract_chunks(doc)

        if not chunks:
            print(f"  SKIP  {doc.document_id[:8]}...  source={source}  (no chunks extracted)")
            continue

        # Generate and append document summary chunk for better aggregation query retrieval
        full_text = "\n\n".join([c["chunk_text"] for c in chunks if c.get("chunk_text")])
        if len(full_text) > 100:
            print(f"  [SUMM] Generating search summary chunk for {doc.document_id[:8]}...")
            summary_text = generate_document_summary(full_text)
            if summary_text:
                chunks.append({
                    "page_number": -1,  # Special page number for document-wide summary
                    "chunk_text": f"[DOCUMENT SUMMARY / STATISTICS / METRICS]\n{summary_text}"
                })

        print(f"  EMBED {doc.document_id[:8]}...  source={source:<12}  chunks={len(chunks)}")

        texts = [c["chunk_text"] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{doc.document_id}-{chunk['page_number']}-{i}"
            ))
            all_points.append(PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "document_id": doc.document_id,
                    "tenant_id": doc.tenant_id,  # RAG Tenant Isolation Fix
                    "source_type": source,
                    "document_purpose": getattr(doc, "document_purpose", "Other") or "Other",
                    "page_number":  chunk["page_number"],
                    "chunk_text":   chunk["chunk_text"],
                    "file_hash":    doc.file_hash,
                },
            ))

        stats[source] = stats.get(source, 0) + len(chunks)

    # Upsert all points
    total_upserted = qc.upsert_chunks(client, all_points)
    total_in_store = qc.get_point_count(client)

    # ── Verification ──────────────────────────────────────────────────────────
    print(f"\n[5] Verification ...")
    print(f"    Points upserted this run   : {total_upserted}")
    print(f"    Total points in collection : {total_in_store}")

    # Check each source type is represented
    print(f"\n    Source-type payload check:")
    source_types_to_check = ["text_native", "scanned_pdf", "image"]
    verification_pass = True
    for st in source_types_to_check:
        hits = qc.query_by_payload(client, "source_type", st, limit=3)
        count = stats.get(st, 0)
        ok = count > 0
        if not ok:
            verification_pass = False
        mark = "[PASS]" if ok else "[FAIL]"
        print(f"    {mark}  source_type={st:<12}  chunks_embedded={count}  queryable={len(hits)>0}")

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print(f"  EMBEDDING REPORT")
    print(SEPARATOR)
    print(f"  Documents processed  : {len(curated_docs)}")
    print(f"  Total chunks embedded: {total_upserted}")
    print(f"  Points in Qdrant     : {total_in_store}")
    print(f"  Breakdown by source type:")
    for src, cnt in sorted(stats.items()):
        print(f"    {src:<15} : {cnt} chunks")
    print(f"  Overall verification : {'PASS' if verification_pass else 'FAIL'}")
    print(SEPARATOR)

    # ── Append metrics ────────────────────────────────────────────────────────
    today = str(date.today())
    breakdown = "  |  ".join(f"{s}: {n}" for s, n in sorted(stats.items()))
    line = (
        f"| {today} | Week 5 – RAG | Qdrant Embedding | "
        f"{total_upserted} points | "
        f"all-MiniLM-L6-v2, {len(curated_docs)} curated docs. "
        f"Breakdown: {breakdown} |\n"
    )
    with open(METRICS_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"\n  metrics.md updated -> {METRICS_FILE}")


if __name__ == "__main__":
    main()
