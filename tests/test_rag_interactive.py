import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from rag.query_classifier import classify_query
from rag.retrieval import retrieve_relevant_chunks
from rag.generation import generate_answer

def main():
    print("=" * 60)
    print("      RAG INTERACTIVE DIAGNOSTIC & VERIFICATION TOOL")
    print("=" * 60)
    
    tenant_id = input("Enter X-Tenant-ID context [default: tenant_audit]: ").strip() or "tenant_audit"
    
    while True:
        query = input("\nEnter your question (or type 'exit' to quit): ").strip()
        if not query or query.lower() == 'exit':
            break
            
        print("\n" + "-" * 50)
        print(f"Query: '{query}'")
        
        # 1. Query Classification
        classification = classify_query(query)
        q_type = classification["type"]
        confidence = classification["confidence"]
        print(f"Detected Query Type : {q_type.upper()} (Confidence: {confidence:.2f})")
        
        # 2. Dynamic Top-K Value Used
        if q_type == "aggregation":
            top_k = 100
        elif q_type == "comparison":
            top_k = 30
        elif q_type == "table_lookup":
            top_k = 20
        else:
            top_k = 5
        print(f"Dynamic Top-K Selected: {top_k}")
        
        # 3. Retrieve Chunks
        print("Retrieving relevant chunks...")
        chunks = retrieve_relevant_chunks(query, tenant_id=tenant_id)
        print(f"Chunks Retrieved from Qdrant: {len(chunks)}")
        
        # 4. Generate Answer
        print("Generating LLM Answer...")
        try:
            res = generate_answer(query, tenant_id=tenant_id)
            
            # Print structured CSV handler usage
            struct_used = res.get("structured_used", False)
            print(f"Structured CSV Handler Used? : {'YES (Pandas Executor)' if struct_used else 'NO (Standard RAG)'}")
            
            print(f"\n[LLM ANSWER]:\n{res.get('answer')}")
            
            print("\n[CITATIONS]:")
            for idx, c in enumerate(res.get("citations", []), 1):
                print(f"  - Citation {idx}: Document: {c['document_id']} (Type: {c['source_type']}, Page/Row: {c['page_number']})")
        except Exception as e:
            print(f"[ERROR]: {e}")
        print("-" * 50)

if __name__ == "__main__":
    main()
