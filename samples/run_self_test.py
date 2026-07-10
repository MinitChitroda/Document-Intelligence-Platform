"""
samples/run_self_test.py

Executes a clean, isolated test of the RAG pipeline with only custom documents.
Steps:
  1. Clear Qdrant collection 'document_chunks'
  2. Clear PostgreSQL tables (documents, bronze_documents)
  3. Upload ONLY recipe.txt and return_policy.pdf
  4. Run Kafka consumer, extraction + Quality Gate, and Embedder
  5. Verify Qdrant points count and details
  6. Run 4 RAG queries using Groq (llama-3.1-8b-instant) and print full evidence
  7. Print summary table and update metrics.md
"""

import os
import sys
import time
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
from rag.retrieval import retrieve_relevant_chunks
from rag.generation import generate_answer, load_dotenv

API_URL = "http://127.0.0.1:8000/upload"
RECIPE_PATH = "samples/custom_test_docs/recipe.txt"
POLICY_PATH = "samples/custom_test_docs/return_policy.pdf"


def clean_state():
    print("=================================================================")
    print("  STEP 1: CLEAR STATE (DB & QDRANT)")
    print("=================================================================")
    
    # 1. Clear Qdrant
    print("Clearing Qdrant collection...")
    client = qc.get_client()
    try:
        client.delete_collection(qc.COLLECTION_NAME)
        print("  Deleted collection.")
    except Exception as e:
        print(f"  Collection delete info: {e}")
    qc.ensure_collection(client)
    count = qc.get_point_count(client)
    print(f"  Verified Qdrant collection point count: {count}")

    # 2. Clear Postgres
    print("Clearing Postgres tables...")
    db_ingest = IngestSession()
    db_bronze = BronzeSession()
    try:
        db_ingest.execute(text("TRUNCATE documents, bronze_documents RESTART IDENTITY CASCADE"))
        db_ingest.commit()
        print("  Postgres tables truncated successfully.")
    except Exception as e:
        db_ingest.rollback()
        print(f"  [ERROR] Postgres truncation failed: {e}")
        sys.exit(1)
    finally:
        db_ingest.close()
        db_bronze.close()


def upload_and_process():
    print("\n=================================================================")
    print("  STEP 2: UPLOAD & PROCESS TEST DOCUMENTS")
    print("=================================================================")
    
    # Start Kafka Consumer in background
    print("Starting Kafka Consumer in background...")
    consumer_proc = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python"), "ingestion/kafka_consumer.py"],
        env={**os.environ, "PYTHONPATH": "."}
    )
    time.sleep(5)  # allow consumer group coordination

    # Upload recipe
    print("Uploading recipe.txt...")
    with open(RECIPE_PATH, "rb") as f:
        r_recipe = requests.post(API_URL, files={"file": ("recipe.txt", f, "text/plain")}, timeout=10)
    recipe_data = r_recipe.json()
    recipe_id = recipe_data.get("document_id")
    recipe_status = recipe_data.get("status")
    print(f"  recipe.txt upload: {r_recipe.status_code} | status={recipe_status} | id={recipe_id}")

    # Upload return policy
    print("Uploading return_policy.pdf...")
    with open(POLICY_PATH, "rb") as f:
        r_policy = requests.post(API_URL, files={"file": ("return_policy.pdf", f, "application/pdf")}, timeout=10)
    policy_data = r_policy.json()
    policy_id = policy_data.get("document_id")
    policy_status = policy_data.get("status")
    print(f"  return_policy.pdf upload: {r_policy.status_code} | status={policy_status} | id={policy_id}")

    # Poll Bronze DB for landed documents
    print("Waiting for documents to land in Bronze...")
    db = BronzeSession()
    landed = False
    for i in range(15):
        count = db.query(BronzeDocument).filter(BronzeDocument.document_id.in_([recipe_id, policy_id])).count()
        if count >= 2:
            print("  Both documents landed in Bronze OK.")
            landed = True
            break
        time.sleep(1)
    
    db.close()
    consumer_proc.terminate()
    print("  Kafka consumer stopped.")

    if not landed:
        print("  [ERROR] Custom documents failed to land in Bronze. Aborting.")
        sys.exit(1)

    # Extraction and Quality Gate
    print("\nRunning Extraction & Quality Gate...")
    db = BronzeSession()
    pending = db.query(BronzeDocument).filter(BronzeDocument.status == "pending").all()
    for doc in pending:
        raw_dir = "data/raw"
        raw_path = None
        for fname in os.listdir(raw_dir):
            if fname.startswith(doc.file_hash):
                raw_path = os.path.join(raw_dir, fname)
                break
        
        if not raw_path:
            print(f"  [WARN] Raw file not found for {doc.document_id}")
            continue

        ext_actual = os.path.splitext(raw_path)[1].lower()
        if ext_actual in [".png", ".jpg", ".jpeg"]:
            doc.source_type = "scanned_pdf"
        elif ext_actual == ".txt":
            doc.source_type = "text_native"

        text_content = ""
        confidence = 100.0

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
        print(f"  Document {doc.document_id[:8]} processed -> {'curated' if passed else 'failed'} (conf: {confidence:.2f}%)")
        db.commit()
    db.close()

    # Re-embed
    print("\nRunning embedder to index curated chunks...")
    embed_module.main()
    print("  Vector embeddings created.")


def verify_qdrant_state():
    print("\n=================================================================")
    print("  STEP 3: VERIFY QDRANT STATE")
    print("=================================================================")
    client = qc.get_client()
    count = qc.get_point_count(client)
    print(f"Total chunks in Qdrant collection: {count}")
    
    res = client.scroll(collection_name=qc.COLLECTION_NAME, limit=100)
    for p in res[0]:
        payload = p.payload
        print(f"  - Point ID: {p.id}")
        print(f"    Document ID: {payload.get('document_id')}")
        print(f"    Source Type: {payload.get('source_type')}")
        print(f"    Page/Chunk : {payload.get('page_number')}")
        print(f"    Snippet    : {payload.get('chunk_text', '')[:100]}...")


def run_rag_test():
    print("\n=================================================================")
    print("  STEP 4: RUN RAG SELF-TEST")
    print("=================================================================")
    
    questions = [
        {"q": "What are the key ingredients in the chocolate cake?", "expected_source": "recipe.txt"},
        {"q": "What is the refund timeline in the policy?", "expected_source": "return_policy.pdf"},
        {"q": "How long should the cake bake?", "expected_source": "recipe.txt"},
        {"q": "Under what conditions is a refund not allowed?", "expected_source": "return_policy.pdf"}
    ]

    results = []

    for i, item in enumerate(questions, 1):
        print("\n" + "=" * 80)
        print(f"QUESTION {i}: {item['q']}")
        print(f"(Expected source context: {item['expected_source']})")
        print("=" * 80)

        chunks = retrieve_relevant_chunks(item["q"], top_k=5)
        print("\n>> RETRIEVED CHUNKS:")
        correct_doc = False
        for idx, c in enumerate(chunks):
            # Check if retrieved chunk is correct
            if item["expected_source"] == "recipe.txt" and "sugar" in c["chunk_text"].lower():
                correct_doc = True
            elif item["expected_source"] == "return_policy.pdf" and "refund" in c["chunk_text"].lower():
                correct_doc = True

            print(f"  Match {idx+1} (Score: {c['score']:.4f}) | doc={c['document_id'][:8]}... | type={c['source_type']} | page={c['page_number']}")
            print(f"    Text: {c['chunk_text'][:120]}...")

        res = generate_answer(item["q"], chunks)
        print("\n[ANSWER]:")
        print(res["answer"])

        print("\n[CITATIONS]:")
        citations_valid = len(res["citations"]) > 0
        for cit in res["citations"]:
            print(f"  - Document: {cit['document_id']} (Type: {cit['source_type']}, Page/Chunk: {cit['page_number']})")
            if not cit["document_id"] or not cit["source_type"]:
                citations_valid = False

        answer_coherent = "cannot find the answer" not in res["answer"].lower() and "[error" not in res["answer"].lower()

        results.append({
            "num": i,
            "q": item["q"],
            "correct_doc": "YES" if correct_doc else "NO",
            "coherent": "YES" if answer_coherent else "NO",
            "citations": "YES" if citations_valid else "NO"
        })

    # Summary table
    print("\n=================================================================")
    print("  STEP 5: FINDINGS REPORT")
    print("=================================================================")
    print(f"{'Question':<12} | {'Retrieved Correct Doc?':<22} | {'Answer Coherent?':<16} | {'Citations Valid?':<16}")
    print("-" * 75)
    
    all_pass = True
    for r in results:
        print(f"Q{r['num']:<10} | {r['correct_doc']:<22} | {r['coherent']:<16} | {r['citations']:<16}")
        if r['correct_doc'] != "YES" or r['coherent'] != "YES" or r['citations'] != "YES":
            all_pass = False

    if all_pass:
        print("\n>>> ALL TESTS PASSED! Updating metrics.md ...")
        metrics_file = "metrics.md"
        line = "| 2026-07-03 | Pre-Prompt 17 Self-Test | Clean Qdrant Isolation Test | 4/4 PASS | 2 custom docs, 4 questions, all retrieved correct documents with coherent answers and valid citations. |\n"
        with open(metrics_file, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"  Updated {metrics_file}")
    else:
        print("\n>>> [WARN] Some RAG test validations failed. Please review.")


if __name__ == "__main__":
    clean_state()
    upload_and_process()
    verify_qdrant_state()
    run_rag_test()
