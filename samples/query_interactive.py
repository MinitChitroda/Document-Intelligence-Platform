"""
samples/query_interactive.py

Interactive CLI tool to ingest a local document/image and ask questions against it.
Flow:
  1. Uploads the file via FastAPI /upload
  2. Runs consumer, extractor, quality gate, and embedder
  3. Enters Q&A loop: User enters query -> Retrieve top-5 from Qdrant -> Generate Answer via Groq

Run from project root:
  $env:PYTHONPATH="."; .venv\Scripts\python samples\query_interactive.py
"""

import os
import sys
import time
import shutil
import subprocess
import requests
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.postgres_bronze import SessionLocal, BronzeDocument
from extraction.text_extraction import extract_text_native
from extraction.ocr.extract import extract_text_ocr
from quality.quality_gate import evaluate_document
import rag.embed as embed_module
import rag.qdrant_store as qc
from rag.retrieval import retrieve_relevant_chunks
from rag.generation import generate_answer, load_dotenv

API_URL = "http://127.0.0.1:8000/upload"


def process_file(file_path: str):
    if not os.path.exists(file_path):
        print(f"[ERROR] Specified file does not exist: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    print(f"\n[1] Uploading '{filename}' to FastAPI /upload ...")
    
    # Determine mime-type
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        mime = "application/pdf"
    elif ext in [".png", ".jpg", ".jpeg"]:
        mime = f"image/{ext.replace('.', '')}"
    elif ext == ".csv":
        mime = "text/csv"
    else:
        mime = "text/plain"

    with open(file_path, "rb") as f:
        try:
            r = requests.post(API_URL, files={"file": (filename, f, mime)}, timeout=10)
            if r.status_code != 200:
                print(f"    Upload failed: {r.status_code} - {r.text}")
                sys.exit(1)
            data = r.json()
            doc_id = data.get("document_id")
            status = data.get("status")
            print(f"    Upload response: {status} | doc_id={doc_id}")
        except Exception as e:
            print(f"    [ERROR] Connection failed: {e}")
            print("    Please make sure uvicorn is running: .venv\\Scripts\\uvicorn ingestion.api:app")
            sys.exit(1)

    if status == "skipped_duplicate":
        print("    File was already processed. Moving directly to QA.")
        return doc_id

    # Run Kafka Consumer
    print("\n[2] Processing events in Kafka Consumer ...")
    consumer_proc = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python"), "ingestion/kafka_consumer.py"],
        env={**os.environ, "PYTHONPATH": "."}
    )
    time.sleep(5)
    consumer_proc.terminate()
    print("    Events processed.")

    # Process extraction
    print("\n[3] Running text extraction and Quality Gate ...")
    db = SessionLocal()
    doc = db.query(BronzeDocument).filter(BronzeDocument.document_id == doc_id).first()
    if not doc:
        print("    [ERROR] Document failed to land in Bronze database.")
        db.close()
        sys.exit(1)

    # Locate raw path
    raw_path = None
    for fname in os.listdir("data/raw"):
        if fname.startswith(doc.file_hash):
            raw_path = os.path.join("data", "raw", fname)
            break
            
    if not raw_path:
        print("    [ERROR] Raw file not found in data/raw")
        db.close()
        sys.exit(1)

    text_content = ""
    confidence = 100.0

    if ext == ".txt":
        with open(raw_path, "r", encoding="utf-8") as f:
            text_content = f.read()
    elif ext == ".pdf":
        # Check if text_native or scanned
        if doc.source_type == "text_native":
            result = extract_text_native(raw_path)
            text_content = " ".join([c["content"] for c in result])
        else:
            result = extract_text_ocr(raw_path)
            text_content = result.get("text", "")
            confidence = result.get("average_confidence", 0.0)
    elif ext in [".png", ".jpg", ".jpeg"]:
        result = extract_text_ocr(raw_path)
        text_content = result.get("text", "")
        confidence = result.get("average_confidence", 0.0)

    doc.extracted_text = text_content
    passed = evaluate_document(db, doc.document_id, raw_path, text_content, confidence)
    print(f"    Document {doc_id[:8]} status set to: {'curated' if passed else 'failed'} (confidence: {confidence:.1f}%)")
    db.commit()
    db.close()

    # Re-run embedder to index the new point
    print("\n[4] Re-indexing curated items into Qdrant vector database ...")
    embed_module.main()
    print("    Vector store updated.")
    return doc_id


def qa_loop():
    print("\n" + "=" * 65)
    print("  INTERACTIVE Q&A SESSION")
    print("  Type 'exit' or 'quit' to close the session.")
    print("=" * 65)
    
    while True:
        try:
            query = input("\nEnter your question: ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit"]:
                print("Closing session. Goodbye!")
                break
                
            print("\n>> Searching Qdrant ...")
            chunks = retrieve_relevant_chunks(query, top_k=5)
            
            print("\n>> Top evidence chunks retrieved:")
            for i, c in enumerate(chunks, 1):
                print(f"  [{i}] Doc: {c['document_id'][:8]}... | Type: {c['source_type']} | Page/Chunk: {c['page_number']} | Score: {c['score']:.4f}")
                snippet = c['chunk_text'][:150].replace('\n', ' ').strip()
                print(f"      Text: \"{snippet}...\"")
                
            print("\n>> Generating Answer from Groq (llama-3.1-8b-instant)...")
            res = generate_answer(query, chunks)
            
            print("\n[ANSWER]:")
            print(res["answer"])
            
            print("\n[CITATIONS]:")
            for cit in res["citations"]:
                print(f"  - Document ID: {cit['document_id']} (Type: {cit['source_type']}, Page/Chunk: {cit['page_number']})")
                
        except KeyboardInterrupt:
            print("\nClosing session. Goodbye!")
            break


def main():
    print("=================================================================")
    print("  INTERACTIVE DOCUMENT INGESTION & Q&A TOOL")
    print("=================================================================")

    # Prompt to clear state
    clear_choice = input("Do you want to clear the existing database and vector store for a clean session? (y/N): ").strip().lower()
    if clear_choice in ["y", "yes"]:
        print("\nClearing Qdrant collection...")
        client = qc.get_client()
        try:
            client.delete_collection(qc.COLLECTION_NAME)
        except Exception:
            pass
        qc.ensure_collection(client)
        print("  Qdrant collection cleared.")

        print("\nClearing Postgres database...")
        from storage.postgres_bronze import SessionLocal as BronzeSession
        from ingestion.idempotency import SessionLocal as IngestSession, Document
        from sqlalchemy import text
        db1 = IngestSession()
        try:
            db1.execute(text("TRUNCATE documents, bronze_documents RESTART IDENTITY CASCADE"))
            db1.commit()
            print("  Postgres tables cleared.")
        except Exception as e:
            db1.rollback()
            print(f"  [ERROR] Failed to clear DB: {e}")
        finally:
            db1.close()

    # Prompt for file path
    default_path = r"C:\Users\LENOVO\Downloads\images.jpeg"
    file_path = input(f"\nEnter the file path to ingest [{default_path}]: ").strip()
    if not file_path:
        file_path = default_path

    # Clean path from quotes
    file_path = file_path.strip("'\"")

    doc_id = process_file(file_path)
    qa_loop()


if __name__ == "__main__":
    main()
