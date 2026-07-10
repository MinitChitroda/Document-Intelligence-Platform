"""
evaluation/setup_evaluation.py

Uploads clean evaluation corpus, processes it through the pipeline,
and dynamically generates evaluation/test_queries.json with correct UUIDs.
"""

import os
import sys
import time
import json
import subprocess
import requests
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.postgres_bronze import SessionLocal as BronzeSession, BronzeDocument
from ingestion.idempotency import SessionLocal as IngestSession, Document
from extraction.text_extraction import extract_text_native
from extraction.ocr.extract import extract_text_ocr
from quality.quality_gate import evaluate_document
import rag.qdrant_store as qc
import rag.embed as embed_module

API_URL = "http://127.0.0.1:8000/upload"

CORPUS = [
    # text_native
    {"filename": "recipe.txt", "path": "samples/custom_test_docs/recipe.txt", "mime": "text/plain", "source_type": "text_native"},
    {"filename": "return_policy.pdf", "path": "samples/custom_test_docs/return_policy.pdf", "mime": "application/pdf", "source_type": "text_native"},
    {"filename": "text_financial_report.pdf", "path": "samples/text_financial_report.pdf", "mime": "application/pdf", "source_type": "text_native"},
    {"filename": "text_incident_report.pdf", "path": "samples/text_incident_report.pdf", "mime": "application/pdf", "source_type": "text_native"},
    {"filename": "text_onboarding_handbook.pdf", "path": "samples/text_onboarding_handbook.pdf", "mime": "application/pdf", "source_type": "text_native"},
    
    # scanned_pdf
    {"filename": "scanned_financial_report.pdf", "path": "samples/scanned_financial_report.pdf", "mime": "application/pdf", "source_type": "scanned_pdf"},
    {"filename": "scanned_onboarding_handbook.pdf", "path": "samples/scanned_onboarding_handbook.pdf", "mime": "application/pdf", "source_type": "scanned_pdf"},
    
    # image
    {"filename": "photographed_spreadsheet.jpg", "path": "samples/photographed_spreadsheet.jpg", "mime": "image/jpeg", "source_type": "image"},
    {"filename": "photographed_receipt_1.png", "path": "samples/photographed_receipt_1.png", "mime": "image/png", "source_type": "image"},
    {"filename": "photographed_receipt_2.jpeg", "path": "samples/photographed_receipt_2.jpeg", "mime": "image/jpeg", "source_type": "image"},
]


def clean_databases():
    print("Clearing Qdrant and Postgres DBs...")
    client = qc.get_client()
    try:
        client.delete_collection(qc.COLLECTION_NAME)
    except Exception:
        pass
    qc.ensure_collection(client)

    # Truncate Ingestion DB
    db_ingest = IngestSession()
    try:
        db_ingest.execute(text("TRUNCATE documents RESTART IDENTITY CASCADE"))
        db_ingest.commit()
        print("  Ingestion documents table truncated.")
    except Exception as e:
        db_ingest.rollback()
        print(f"Error truncating Ingestion DB: {e}")
        sys.exit(1)
    finally:
        db_ingest.close()

    # Truncate Bronze DB
    db_bronze = BronzeSession()
    try:
        db_bronze.execute(text("TRUNCATE bronze_documents RESTART IDENTITY CASCADE"))
        db_bronze.commit()
        print("  Bronze bronze_documents table truncated.")
    except Exception as e:
        db_bronze.rollback()
        print(f"Error truncating Bronze DB: {e}")
        sys.exit(1)
    finally:
        db_bronze.close()


def ingest_corpus():
    print("Starting Kafka Consumer in background...")
    consumer_proc = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python"), "ingestion/kafka_consumer.py"],
        env={**os.environ, "PYTHONPATH": "."}
    )
    time.sleep(5)

    doc_mappings = {}

    for doc in CORPUS:
        print(f"Uploading {doc['filename']}...")
        with open(doc['path'], "rb") as f:
            r = requests.post(API_URL, files={"file": (doc['filename'], f, doc['mime'])}, timeout=10)
        res_data = r.json()
        doc_id = res_data.get("document_id")
        doc_mappings[doc['filename']] = doc_id
        print(f"  ID: {doc_id}")

    # Wait for Bronze
    print("Waiting for files to land in Bronze...")
    db = BronzeSession()
    for i in range(15):
        count = db.query(BronzeDocument).count()
        if count >= len(CORPUS):
            print("  All documents in Bronze.")
            break
        time.sleep(1)
    
    db.close()
    consumer_proc.terminate()
    print("Consumer stopped.")

    # Processing (extract & quality gate)
    print("Running extraction and quality gate...")
    db = BronzeSession()
    pending = db.query(BronzeDocument).filter(BronzeDocument.status == "pending").all()
    for doc in pending:
        # Resolve raw path
        raw_path = None
        for fname in os.listdir("data/raw"):
            if fname.startswith(doc.file_hash):
                raw_path = os.path.join("data", "raw", fname)
                break
        if not raw_path:
            continue

        text_content = ""
        confidence = 100.0

        # Extract
        if raw_path.endswith(".txt"):
            with open(raw_path, "r", encoding="utf-8") as f:
                text_content = f.read()
        elif doc.source_type == "text_native":
            result = extract_text_native(raw_path)
            text_content = " ".join([c["content"] for c in result])
        elif doc.source_type in ["scanned_pdf", "scanned"]:
            result = extract_text_ocr(raw_path)
            text_content = result.get("text", "")
            confidence = result.get("average_confidence", 0.0)

        doc.extracted_text = text_content
        passed = evaluate_document(db, doc.document_id, raw_path, text_content, confidence)
        db.commit()
    
    db.close()

    print("Embedding points...")
    embed_module.main()
    print("Embeddings generated.")
    return doc_mappings


def generate_queries_json(doc_mappings):
    print("Generating queries JSON file...")
    
    raw_queries = [
        # text_native (10 queries)
        {
            "question": "What is the baking temperature for the chocolate cake?",
            "file": "recipe.txt", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "List all ingredients needed for the chocolate cake.",
            "file": "recipe.txt", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "How long should the chocolate cake bake?",
            "file": "recipe.txt", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "What is the refund timeline?",
            "file": "return_policy.pdf", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "Under what conditions is a refund not allowed?",
            "file": "return_policy.pdf", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "How long does a customer have to return a product?",
            "file": "return_policy.pdf", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "What is the total revenue for Q3 2024?",
            "file": "text_financial_report.pdf", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "What was the net income for Acme Corporation in Q3 2024?",
            "file": "text_financial_report.pdf", "type": "text_native", "page": 0, "difficulty": "easy"
        },
        {
            "question": "How much was the operating cash flow in Q3 2024?",
            "file": "text_financial_report.pdf", "type": "text_native", "page": 0, "difficulty": "medium"
        },
        {
            "question": "What was the net margin of Acme Corporation in Q3 2024?",
            "file": "text_financial_report.pdf", "type": "text_native", "page": 0, "difficulty": "medium"
        },

        # scanned_pdf (9 queries)
        {
            "question": "What is the dress code policy?",
            "file": "scanned_onboarding_handbook.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "easy"
        },
        {
            "question": "How many hours of training must new hires complete?",
            "file": "scanned_onboarding_handbook.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "easy"
        },
        {
            "question": "Who should employees contact for IT support?",
            "file": "scanned_onboarding_handbook.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "easy"
        },
        {
            "question": "What is the core working hours policy?",
            "file": "scanned_onboarding_handbook.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "medium"
        },
        {
            "question": "Are remote work days allowed under the policy?",
            "file": "scanned_onboarding_handbook.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "medium"
        },
        {
            "question": "What are the planned capital expenditures for Acme Corporation?",
            "file": "scanned_financial_report.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "medium"
        },
        {
            "question": "What is the full-year 2024 revenue guidance for Acme?",
            "file": "scanned_financial_report.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "medium"
        },
        {
            "question": "What is the revenue guidance for Q4 2024?",
            "file": "scanned_financial_report.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "medium"
        },
        {
            "question": "Explain the difference in revenue growth across different reports.",
            "file": "scanned_financial_report.pdf", "type": "scanned_pdf", "page": 0, "difficulty": "hard"
        },

        # image (3 queries)
        {
            "question": "What is the payment method used for the Hinduja College payment?",
            "file": "photographed_receipt_2.jpeg", "type": "image", "page": 0, "difficulty": "easy"
        },
        {
            "question": "What is the total payment amount shown on the Federal Bank receipt?",
            "file": "photographed_receipt_1.png", "type": "image", "page": 0, "difficulty": "medium"
        },
        {
            "question": "What is the payment date on the Federal Bank receipt?",
            "file": "photographed_receipt_1.png", "type": "image", "page": 0, "difficulty": "medium"
        }
    ]

    final_queries = []
    for rq in raw_queries:
        uuid_val = doc_mappings.get(rq["file"])
        if not uuid_val:
            print(f"[WARN] No UUID mapping found for file {rq['file']}")
            continue
        final_queries.append({
            "question": rq["question"],
            "expected_document_id": uuid_val,
            "expected_source_type": rq["type"],
            "expected_page": rq["page"],
            "difficulty": rq["difficulty"]
        })

    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/test_queries.json", "w", encoding="utf-8") as f:
        json.dump(final_queries, f, indent=2)
    print("evaluation/test_queries.json generated successfully.")


if __name__ == "__main__":
    clean_databases()
    mappings = ingest_corpus()
    generate_queries_json(mappings)
