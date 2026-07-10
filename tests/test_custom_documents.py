import os
import re
import sys
import time
import requests
from sqlalchemy.orm import Session
from storage.postgres_bronze import SessionLocal, BronzeDocument

# Force stdout to use utf-8 if supported to prevent Windows CP1252 print crashes
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# USER CONFIGURATION - EDIT THESE PATHS
TEST_DOCUMENTS = {
    "csv": r"C:\Users\LENOVO\Downloads\D J Sanghvi - SDE.csv",
    "pdf": r"C:\Users\LENOVO\Downloads\Gmail - TCS NQT for Priority Institutes Batch 2027_ 29th June 2026.pdf",
    "image": r"C:\Users\LENOVO\Downloads\WhatsApp Image 2026-05-05 at 10.24.13 PM.jpeg",
    "multi_page_pdf": r"C:\Users\LENOVO\Downloads\Gmail - TCS NQT for Priority Institutes Batch 2027_ 29th June 2026.pdf"
}

TENANT_ID = "tenant_001"

# Automatically use port 8001 as verified by run_app.py config
API_URL = "http://localhost:8001"

TEST_SUITE = [
    {
        "test_num": 1,
        "issue": "Incorrect Context Retrieval",
        "file_type": "pdf",
        "query": "What are the reporting time, gate closure time, examination venue, and mandatory documents required for the TCS NQT examination?",
        "expected_behavior": "Retrieve the exact examination details with proper citations.",
        "verify": "Answer matches the uploaded PDF."
    },
    {
        "test_num": 2,
        "issue": "Inadequate Multi-Document Retrieval",
        "file_type": "any",
        "query": "Summarize all uploaded documents.",
        "expected_behavior": "Summarize the CSV, PDF, and image together.",
        "verify": "All three uploaded documents are included in the summary."
    },
    {
        "test_num": 3,
        "issue": "Weak Semantic Retrieval",
        "file_type": "image",
        "query": "Summarize the payment receipt and list all important transaction details.",
        "expected_behavior": "Extract all payment details from the receipt.",
        "verify": "Amount, sender, receiver, UPI ID, Google Transaction ID, date and payment status are correctly extracted."
    },
    {
        "test_num": 4,
        "issue": "Weak Handling of Structured Data",
        "file_type": "csv",
        "query": "Which engineering branches are represented in the student CSV, and how many students belong to each branch?",
        "expected_behavior": "Return every branch along with the correct student count.",
        "verify": "Counts exactly match the CSV."
    },
    {
        "test_num": 5,
        "issue": "Limited Evidence-Based Reasoning",
        "file_type": "any",
        "query": "Which uploaded document contains student information, which contains examination instructions, and which contains payment information? Explain your reasoning using evidence from each document.",
        "expected_behavior": "Correctly identify all three document types using evidence from each document.",
        "verify": "Uses all three uploaded documents with supporting citations."
    },
    {
        "test_num": 6,
        "issue": "Response Generation from Incorrect Context",
        "file_type": "pdf",
        "query": "What is the dress code for the TCS examination?",
        "expected_behavior": "System should abstain because no such information exists.",
        "verify": "No hallucination; clearly states insufficient evidence."
    },
    {
        "test_num": 7,
        "issue": "Unsupported Inference",
        "file_type": "image",
        "query": "Why did the student make this payment?",
        "expected_behavior": "System should refuse to speculate because the receipt does not contain that information.",
        "verify": "No assumptions beyond the document."
    },
    {
        "test_num": 8,
        "issue": "Weak Cross-Context Reasoning",
        "file_type": "any",
        "query": "Identify which uploaded document is related to academics, which is related to recruitment, and which is related to financial transactions.",
        "expected_behavior": "Correctly classify each document.",
        "verify": "Uses evidence from all uploaded documents."
    },
    {
        "test_num": 9,
        "issue": "Missing Confidence-Based Response Control",
        "file_type": "any",
        "query": "What is the weather on the day of the examination?",
        "expected_behavior": "System should abstain due to lack of evidence.",
        "verify": "Returns low confidence or insufficient evidence."
    },
    {
        "test_num": 10,
        "issue": "Citation and Evidence Presentation",
        "file_type": "pdf",
        "query": "List all documents a candidate must carry to the TCS examination centre.",
        "expected_behavior": "Every requirement should be cited from the uploaded PDF.",
        "verify": "Answer includes proper citations."
    },
    {
        "test_num": 11,
        "issue": "Weak Abstention Behaviour",
        "file_type": "any",
        "query": "Who won the FIFA World Cup in 2022?",
        "expected_behavior": "System should refuse to answer because the information is not contained in the uploaded documents.",
        "verify": "No hallucination."
    },
    {
        "test_num": 12,
        "issue": "Limited Analytical Query Support",
        "file_type": "csv",
        "query": "Compare the number of students enrolled in each engineering branch and identify which branch has the highest enrollment.",
        "expected_behavior": "Perform structured aggregation over the CSV and identify the largest branch.",
        "verify": "Counts and highest-enrollment branch are correct."
    }
]

def upload_test_documents() -> dict:
    """Reads each file from TEST_DOCUMENTS paths, uploads via FastAPI, and waits for curation."""
    uploaded_ids = {}
    print("\n" + "="*80)
    print("PART 1: UPLOADING CUSTOM DOCUMENTS")
    print("="*80)

    # Validate paths first
    for name, path in TEST_DOCUMENTS.items():
        if not os.path.exists(path):
            print(f"[FAIL] Error: Local file not found at: {path}")
            sys.exit(1)

    for name, path in TEST_DOCUMENTS.items():
        filename = os.path.basename(path)
        print(f"Uploading {name}: {filename} ...")
        
        # Open and upload
        with open(path, "rb") as f:
            files = {"file": (filename, f.read())}
        
        headers = {"X-Tenant-ID": TENANT_ID}
        try:
            response = requests.post(f"{API_URL}/upload", files=files, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                doc_id = result.get("document_id")
                uploaded_ids[name] = doc_id
                print(f"[OK] Uploaded: {filename} -> Document ID: {doc_id}")
            else:
                print(f"[FAIL] Upload failed for {filename}: Status {response.status_code} - {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"[FAIL] Connection error during upload of {filename}: {e}")
            sys.exit(1)

    # Poll postgres DB until status transitions out of pending
    print("\nWaiting for Ingestion pipeline to process, validate, and embed chunks...")
    db = SessionLocal()
    pending_ids = list(uploaded_ids.values())
    start_time = time.time()
    max_wait = 180  # 3 mins

    while pending_ids and (time.time() - start_time) < max_wait:
        for doc_id in list(pending_ids):
            doc = db.query(BronzeDocument).filter(BronzeDocument.document_id == doc_id).first()
            if doc:
                if doc.status in ("curated", "failed"):
                    print(f"  - Document {doc.filename} ({doc_id[:8]}...) -> {doc.status.upper()}")
                    pending_ids.remove(doc_id)
            time.sleep(0.5)
        if pending_ids:
            time.sleep(2.0)
    db.close()

    if pending_ids:
        print("[WARN] Timeout waiting for documents to process. Continuing to query...")
    else:
        print("[OK] Ingestion and embedding completed successfully!")
    
    return uploaded_ids

def run_custom_test(test_config: dict) -> tuple[str, str]:
    """Execute a test config against the RAG API, print results, and request manual evaluation."""
    print(f"\n{'='*80}")
    print(f"TEST {test_config['test_num']}: {test_config['issue']}")
    print(f"{'='*80}")
    print(f"Document Type: {test_config['file_type']}")
    
    file_path = TEST_DOCUMENTS.get(test_config['file_type'], "Multiple Documents")
    print(f"File Path: {file_path}")
    print(f"\nYour Query: {test_config['query']}")
    print(f"Expected: {test_config['expected_behavior']}")
    
    # Call RAG API (params instead of json to match FastAPI Query syntax)
    try:
        response = requests.post(
            f"{API_URL}/query",
            params={"query": test_config['query']},
            headers={"X-Tenant-ID": TENANT_ID},
            timeout=45
        )
        if response.status_code != 200:
            print(f"[FAIL] API Error {response.status_code}: {response.text}")
            return "ERROR", "API Error"
        
        result = response.json()
    except Exception as e:
        print(f"[FAIL] Connection error: {e}")
        return "ERROR", f"Connection error: {e}"
    
    print(f"\n{'-'*80}")
    print("RESULTS:")
    print(f"{'-'*80}")
    print(f"Answer:\n{result['answer']}")
    
    chunks_used = len(result.get('chunks', []))
    print(f"\nChunks Retrieved: {chunks_used}")
    print(f"Confidence: {result['confidence']}")
    print(f"Routing Path: {result['routing_path']}")
    print(f"Abstained: {result.get('abstained', False)}")
    if result.get("structured_query_executed"):
        print(f"Query Executed: {result['structured_query_executed']}")
    
    print(f"\nCitations:")
    citations = result.get('citations', [])
    if not citations:
        print("  No citations.")
    for i, citation in enumerate(citations, 1):
        doc_id = citation.get('document_id', 'unknown')
        page_num = citation.get('page_number', citation.get('page', 0))
        filename = citation.get('filename', 'unknown')
        
        # Retrieve snippet from chunks to print quote
        snippet = ""
        for chunk in result.get('chunks', []):
            if chunk.get('document_id') == doc_id and chunk.get('page_number') == page_num:
                snippet = chunk.get('chunk_text', '')
                break
        if not snippet:
            snippet = "No text snippet available"
            
        print(f"  [{i}] Document {doc_id[:8]}... ({filename}), Page/Row {page_num}")
        print(f"      Quote: {snippet[:120]}...")
    
    print(f"\n{'-'*80}")
    print("VERIFICATION:")
    print(f"{'-'*80}")
    print(f"Expected Behavior: {test_config['expected_behavior']}")
    print(f"Verification Criteria: {test_config['verify']}")
    print(f"\nDoes this test PASS or FAIL?")
    print(f"  [PASS] -- Behavior matches expectation")
    print(f"  [FAIL] -- Behavior does not match")
    
    while True:
        manual_result = input("Enter PASS or FAIL: ").strip().upper()
        if manual_result in ("PASS", "FAIL"):
            break
        print("Invalid input. Please enter exactly 'PASS' or 'FAIL'.")
        
    return manual_result, result['answer']

def main():
    uploaded_ids = upload_test_documents()
    
    results = []
    passed_count = 0
    failed_count = 0
    
    print("\n" + "="*80)
    print("PART 2 & 3: RUNNING 12 CUSTOM TESTS")
    print("="*80)
    
    for tc in TEST_SUITE:
        status, answer = run_custom_test(tc)
        results.append({
            "num": tc["test_num"],
            "issue": tc["issue"],
            "query": tc["query"],
            "answer": answer,
            "status": status
        })
        if status == "PASS":
            passed_count += 1
        elif status == "FAIL":
            failed_count += 1
            
    # Write Custom Test Results Report
    report_path = "CUSTOM_TEST_RESULTS.md"
    print(f"\nWriting test report to: {report_path} ...")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Custom Document Testing Report\n\n")
        f.write("## Test Documents Used\n")
        f.write(f"- **CSV**: `{TEST_DOCUMENTS['csv']}`\n")
        f.write(f"- **PDF**: `{TEST_DOCUMENTS['pdf']}`\n")
        f.write(f"- **Image**: `{TEST_DOCUMENTS['image']}`\n")
        f.write(f"- **Multi-Page PDF**: `{TEST_DOCUMENTS['multi_page_pdf']}`\n\n")
        
        f.write("## Test Results\n\n")
        f.write("| Test | Issue | Your Query | Result | Status |\n")
        f.write("|------|-------|-----------|--------|--------|\n")
        for r in results:
            cleaned_answer = r["answer"].replace("\n", " ").replace("|", "\\|")
            status_emoji = "✅ PASS" if r["status"] == "PASS" else "❌ FAIL"
            f.write(f"| {r['num']} | {r['issue']} | {r['query']} | {cleaned_answer[:120]}... | {status_emoji} |\n")
            
        f.write("\n## Summary\n")
        f.write(f"- **Total Tests**: 12\n")
        f.write(f"- **Passed**: {passed_count}\n")
        f.write(f"- **Failed**: {failed_count}\n")
        
        all_fixed = "YES" if failed_count == 0 else "NO"
        f.write(f"- **All Issues Fixed**: {all_fixed}\n")
        
        if failed_count > 0:
            f.write("\n## Failed Tests Details\n")
            for r in results:
                if r["status"] == "FAIL":
                    f.write(f"### Test {r['num']}: {r['issue']}\n")
                    f.write(f"- **Query**: {r['query']}\n")
                    f.write(f"- **Answer Generated**:\n```\n{r['answer']}\n```\n\n")
                    
    print(f"[OK] Report successfully generated at {report_path}!")

if __name__ == "__main__":
    main()
