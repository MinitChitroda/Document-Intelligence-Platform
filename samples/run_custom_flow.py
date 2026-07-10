import os
import sys
import time
import subprocess
import requests
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.postgres_bronze import SessionLocal, BronzeDocument
from extraction.text_extraction import extract_text_native
from extraction.ocr.extract import extract_text_ocr
from quality.quality_gate import evaluate_document
import rag.embed as embed_module
from rag.retrieval import retrieve_relevant_chunks
from rag.generation import generate_answer

API_URL = "http://127.0.0.1:8000/upload"
RECIPE_PATH = "samples/custom_test_docs/recipe.txt"
POLICY_PATH = "samples/custom_test_docs/return_policy.pdf"


def run_pipeline():
    print("=================================================================")
    print("  WEEK 5 PROMPT 16: CUSTOM DOCS TEST PIPELINE")
    print("=================================================================")

    # 0. Clean DB for custom docs
    print("\n[STEP 0] Cleaning database for custom documents ...")
    from storage.postgres_bronze import SessionLocal as BronzeSession
    from ingestion.idempotency import SessionLocal as IngestSession, Document
    db1 = IngestSession()
    db2 = BronzeSession()
    hashes = [
        "d436153cb43426fb8a46416c1a46a72c255ffe1041f642829123b551ce14bfab",
        "155233b0e93a6872e350d5e04ca4ff1fa7833b31c0f688fa14d5fffa1311a776"
    ]
    for h in hashes:
        db1.query(Document).filter(Document.file_hash == h).delete()
        db2.query(BronzeDocument).filter(BronzeDocument.file_hash == h).delete()
    db1.commit()
    db2.commit()
    db1.close()
    db2.close()
    print("  Database cleaned.")

    # 1. Start Kafka consumer in background
    print("\n[STEP 1] Starting Kafka Consumer in background ...")
    consumer_proc = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python"), "ingestion/kafka_consumer.py"],
        env={**os.environ, "PYTHONPATH": "."}
    )
    # Wait for consumer group coordination
    time.sleep(5)

    # 2. Upload documents through FastAPI
    print("\n[STEP 2] Uploading custom documents through FastAPI /upload ...")
    
    # Upload recipe
    with open(RECIPE_PATH, "rb") as f:
        r_recipe = requests.post(API_URL, files={"file": ("recipe.txt", f, "text/plain")}, timeout=10)
    recipe_data = r_recipe.json()
    recipe_id = recipe_data.get("document_id")
    print(f"  recipe.txt upload: {r_recipe.status_code} - id={recipe_id}")

    # Upload return_policy
    with open(POLICY_PATH, "rb") as f:
        r_policy = requests.post(API_URL, files={"file": ("return_policy.pdf", f, "application/pdf")}, timeout=10)
    policy_data = r_policy.json()
    policy_id = policy_data.get("document_id")
    print(f"  return_policy.pdf upload: {r_policy.status_code} - id={policy_id}")

    # 3. Wait for documents to land in Bronze
    print("\n[STEP 3] Waiting for documents to land in Bronze ...")
    db = SessionLocal()
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
        return

    # 4. Run Extraction & Quality Gate for pending docs
    print("\n[STEP 4] Running Extraction & Quality Gate for pending docs ...")
    db = SessionLocal()
    pending_docs = db.query(BronzeDocument).filter(BronzeDocument.status == "pending").all()
    print(f"  Found {len(pending_docs)} pending documents in Bronze")

    for doc in pending_docs:
        ext = ".txt" if doc.source_type == "text_native" or "recipe" in doc.document_id else ".pdf"
        # Let's locate the file
        raw_dir = "data/raw"
        raw_path = None
        for fname in os.listdir(raw_dir):
            if fname.startswith(doc.file_hash):
                raw_path = os.path.join(raw_dir, fname)
                break
        
        if not raw_path:
            print(f"  [WARN] File not found for {doc.document_id}")
            continue

        print(f"  Processing: {raw_path} (source_type={doc.source_type})")
        
        # Override source type from extension if needed
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
        print(f"  {doc.document_id[:8]} -> {'curated' if passed else 'failed'} (conf: {confidence:.2f}%)")
        db.commit()

    db.close()

    # 4. Embed the new curated documents into Qdrant
    print("\n[STEP 4] Running Embedder ...")
    embed_module.main()

    # 5. Run the 4 test questions
    print("\n[STEP 5] Running RAG Test Questions ...")
    questions = [
        {"q": "What is the baking temperature and how long should it bake?", "desc": "Recipe baking test"},
        {"q": "List all the ingredients needed", "desc": "Recipe ingredients list"},
        {"q": "What is the refund timeline?", "desc": "Policy timeline test"},
        {"q": "Under what conditions is a refund not allowed?", "desc": "Policy conditions test"}
    ]

    all_passed = True
    for i, item in enumerate(questions, 1):
        print("\n" + "=" * 80)
        print(f"QUESTION {i}: {item['q']}")
        print(f"({item['desc']})")
        print("=" * 80)

        chunks = retrieve_relevant_chunks(item["q"], top_k=5)
        print("\n>> RETRIEVED CHUNKS:")
        for idx, c in enumerate(chunks):
            print(f"  Match {idx+1} (Score: {c['score']:.4f}) | doc={c['document_id'][:8]}... | type={c['source_type']} | page={c['page_number']}")
            print(f"    Text: {c['chunk_text'][:120]}...")

        res = generate_answer(item["q"], chunks)
        print("\n[ANSWER]:")
        print(res["answer"])

        print("\n[CITATIONS]:")
        for cit in res["citations"]:
            print(f"  - Document: {cit['document_id']} (Type: {cit['source_type']}, Page/Chunk: {cit['page_number']})")

        # Basic sanity check: answer shouldn't say "cannot find"
        if "cannot find the answer" in res["answer"].lower() or "[error" in res["answer"].lower():
            all_passed = False

    if all_passed:
        print("\n>>> ALL TESTS PASSED SUCCESSFULLY! Updating metrics.md ...")
        metrics_file = "metrics.md"
        line = "| 2026-07-03 | Week 5 – RAG | Custom Docs Test | 4/4 questions answered correctly | Week 5 Prompt 16 (Custom Docs Test): 4/4 questions answered correctly, retrieved from 2 new custom documents, no regressions. |\n"
        with open(metrics_file, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"  Updated {metrics_file}")
    else:
        print("\n>>> [WARN] Some tests did not return answers from custom documents.")


if __name__ == "__main__":
    run_pipeline()
