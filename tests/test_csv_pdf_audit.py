import os
import time
import requests
import pandas as pd

API_URL = "http://localhost:8001"

def clean_and_prepare_csv(source_path, target_filename="temp_cleaned.csv"):
    df = pd.read_csv(source_path)
    df = df.dropna(how='all')
    df.to_csv(target_filename, index=False)
    return target_filename

def upload_file(filepath, tenant_id):
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        files = {"file": (filename, f)}
        headers = {"X-Tenant-ID": tenant_id}
        res = requests.post(f"{API_URL}/upload", files=files, headers=headers)
        data = res.json()
        print(f"\nUploaded {filename} -> Status: {data.get('status')} | Document ID: {data.get('document_id')}")
        return data.get("document_id")

def run_query(query, tenant_id):
    headers = {"X-Tenant-ID": tenant_id}
    res = requests.post(f"{API_URL}/query", params={"query": query}, headers=headers)
    return res.json()

def main():
    print("=" * 60)
    print("        INTERACTIVE RAG PIPELINE AUDITOR & TESTER")
    print("=" * 60)
    
    tenant_id = input("Enter X-Tenant-ID context [default: tenant_audit]: ").strip() or "tenant_audit"
    
    # Get CSV path
    csv_path = input("Enter path to a CSV file to upload (leave empty to skip): ").strip()
    # Strip quotes if user dragged-and-dropped the file into the terminal
    csv_path = csv_path.strip("'\"")
    
    csv_doc_id = None
    if csv_path:
        if not os.path.exists(csv_path):
            print(f"[ERROR] File not found: {csv_path}")
            return
        temp_csv = "temp_cleaned_audit.csv"
        try:
            clean_and_prepare_csv(csv_path, temp_csv)
            csv_doc_id = upload_file(temp_csv, tenant_id)
            try:
                os.remove(temp_csv)
            except:
                pass
        except Exception as e:
            print(f"[ERROR] Failed to clean/upload CSV: {e}")
            return
            
    # Get PDF path
    pdf_path = input("Enter path to a PDF file to upload (leave empty to skip): ").strip()
    pdf_path = pdf_path.strip("'\"")
    
    pdf_doc_id = None
    if pdf_path:
        if not os.path.exists(pdf_path):
            print(f"[ERROR] File not found: {pdf_path}")
            return
        try:
            pdf_doc_id = upload_file(pdf_path, tenant_id)
        except Exception as e:
            print(f"[ERROR] Failed to upload PDF: {e}")
            return
            
    if csv_doc_id or pdf_doc_id:
        print("\nWaiting 15 seconds for Kafka inline consumer to ingest and embed document chunks...")
        time.sleep(15)
        
    print("\n" + "=" * 60)
    print("                    QUERY INTERFACE")
    print("=" * 60)
    
    while True:
        query = input("\nEnter your question (or type 'exit' to quit): ").strip()
        if not query or query.lower() == 'exit':
            break
            
        print(f"\n>> Sending query to API with Tenant: '{tenant_id}'...")
        try:
            res = run_query(query, tenant_id)
            if "detail" in res:
                print(f"[API ERROR]: {res['detail']}")
                continue
                
            print(f"\n[LLM ANSWER]:\n{res.get('answer')}")
            
            print("\n[CITATIONS]:")
            chunks = res.get("chunks", [])
            if not chunks:
                print("  No citation chunks returned.")
            for idx, c in enumerate(chunks, 1):
                print(f"  [{idx}] Score: {c.get('score', 0.0):.4f} | Source: {c.get('source_type')} | Page/Row: {c.get('page_number')}")
                print(f"      Snippet: {c.get('chunk_text', '')[:200]}...")
        except Exception as e:
            print(f"[ERROR] Query failed: {e}")

if __name__ == "__main__":
    main()
