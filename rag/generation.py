"""
rag/generation.py

Generates answers using the Groq API (llama3-8b-8192) given retrieved chunks as context.
Tests the retrieval and generation pipeline on 3 concrete questions.
"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.retrieval import retrieve_relevant_chunks
from rag.groq_client import get_groq_manager
groq_manager = get_groq_manager()

def generate_answer(query: str, tenant_id_or_chunks = None, chunks: list[dict] = None, tenant_id: str = None) -> dict:
    """
    Format prompt with retrieved context chunks, call Groq API, and format response.
    Supports both generate_answer(query, chunks) and generate_answer(query, tenant_id).
    """
    if isinstance(tenant_id_or_chunks, str) and tenant_id is None:
        tenant_id = tenant_id_or_chunks
    elif isinstance(tenant_id_or_chunks, list):
        chunks = tenant_id_or_chunks

    if chunks and not tenant_id:
        tenant_id = chunks[0].get("tenant_id")

    from rag.query_classifier import classify_query
    from rag.csv_handler import handle_csv_aggregation
    from storage.postgres_bronze import SessionLocal, BronzeDocument
    from rag.embed import resolve_raw_path

    # Classify the query
    classification = classify_query(query)
    q_type = classification["type"]

    # Check if there is a CSV document curated for this tenant
    import pandas as pd
    db = SessionLocal()
    csv_docs = []
    if tenant_id:
        csv_docs = db.query(BronzeDocument).filter(
            BronzeDocument.tenant_id == tenant_id,
            BronzeDocument.status == "curated",
            BronzeDocument.source_type == "csv"
        ).order_by(BronzeDocument.created_at.desc()).all()
    db.close()

    csv_doc = None
    if csv_docs:
        # Default to the most recently uploaded CSV
        csv_doc = csv_docs[0]
        # Inspect headers to find the best match for the query
        for doc in csv_docs:
            raw_path = resolve_raw_path(doc.file_hash)
            if raw_path:
                try:
                    df_cols = pd.read_csv(raw_path, nrows=0).columns
                    df_cols = [c.strip().lower() for c in df_cols]
                    query_words = query.lower().split()
                    matched = False
                    for col in df_cols:
                        for word in query_words:
                            if word in col or col in word:
                                matched = True
                                break
                        if matched:
                            break
                    if matched:
                        csv_doc = doc
                        break
                except Exception:
                    pass

    structured_res = None
    structured_used = False
    if csv_doc and q_type == "aggregation":
        raw_path = resolve_raw_path(csv_doc.file_hash)
        if raw_path:
            structured_res = handle_csv_aggregation(query, raw_path, csv_doc.document_id)

    # Use structured Pandas result if available, else standard chunks retrieval
    if structured_res:
        structured_used = True
        chunks_used = [{
            "document_id": structured_res["document_id"],
            "source_type": "csv",
            "page_number": 0,
            "chunk_text": structured_res["data"]
        }]
    else:
        # If chunks were not passed, retrieve them dynamically using Part 2
        if chunks is None:
            chunks = retrieve_relevant_chunks(query, tenant_id=tenant_id)
        chunks_used = chunks

    # Map document IDs to filenames and timestamps
    doc_ids = list(set(chunk["document_id"] for chunk in chunks_used))
    doc_metadata = {}
    if doc_ids:
        db = SessionLocal()
        meta_rows = db.query(BronzeDocument).filter(BronzeDocument.document_id.in_(doc_ids)).all()
        for r in meta_rows:
            doc_metadata[r.document_id] = {
                "filename": r.filename or f"Document_{r.document_id[:8]}",
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "Unknown"
            }
        db.close()

    context_parts = []
    if structured_res:
        meta = doc_metadata.get(structured_res['document_id'], {"filename": f"Document_{structured_res['document_id'][:8]}", "created_at": "Unknown"})
        context_str = (
            f"=== SOURCE DOCUMENT: {meta['filename']} (Uploaded: {meta['created_at']}) ===\n"
            f"Document ID: {structured_res['document_id']}\n"
            f"Structured Aggregation Content: {structured_res['data']}\n"
        )
    else:
        # Group chunks by document to prevent cross-contamination
        chunks_by_doc = {}
        for chunk in chunks_used:
            doc_id = chunk["document_id"]
            if doc_id not in chunks_by_doc:
                chunks_by_doc[doc_id] = []
            chunks_by_doc[doc_id].append(chunk)

        for doc_id, doc_chunks in chunks_by_doc.items():
            meta = doc_metadata.get(doc_id, {"filename": f"Document_{doc_id[:8]}", "created_at": "Unknown"})
            context_parts.append(f"=== SOURCE DOCUMENT: {meta['filename']} (Uploaded: {meta['created_at']}) ===")
            for j, chunk in enumerate(doc_chunks):
                context_parts.append(
                    f"--- Chunk {j+1} ---\n"
                    f"Page/Row Number: {chunk['page_number']}\n"
                    f"Text Content: {chunk['chunk_text']}"
                )
            context_parts.append("")  # spacing
        context_str = "\n".join(context_parts)

    system_prompt = (
        "You are a precise, helpful document retrieval and QA assistant. "
        "Answer the question based ONLY on the provided context documents. "
        "Rules:\n"
        "1. Cite the source document filename and page/row number for every fact you state (e.g., 'Source: College_Fee_Receipt.pdf, Page 1'). Do not use internal Document ID UUIDs in your text.\n"
        "2. Group and synthesize facts logically. Avoid cross-document contamination: never merge numerical amounts, dates, or transaction details from unrelated source documents.\n"
        "3. Synthesize the facts into a fluent, cohesive explanation (narrative flow). Explain sequences naturally (e.g., describing initiation, transit, and receipt confirmation) instead of just listing reordered bullet points.\n"
        "4. If context chunks contain conflicting values (e.g., different payment amounts or status values for similar queries), prioritize the document with the most recent Uploaded timestamp, or explicitly call out the conflict.\n"
        "5. Be helpful and make direct, obvious deductions where appropriate (e.g., recognizing Virtual Payment Addresses / UPI handles ending in @icici or @okicici as payment handles/identities, or general details in the document).\n"
        "6. If the context does not contain the answer, clearly state: 'I cannot find the answer based on the provided context.' Do not make up any information."
    )

    user_prompt = (
        f"Context documents:\n{context_str}\n\n"
        f"Question: {query}\n"
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        answer = groq_manager.call_with_fallback(messages, "llama-3.1-8b-instant", 0.2)
    except Exception as e:
        answer = f"[ERROR calling Groq API]: {e}"

    # Extract unique citations from chunks
    citations = []
    seen = set()
    for chunk in chunks_used:
        meta = doc_metadata.get(chunk["document_id"], {"filename": f"Document_{chunk['document_id'][:8]}", "created_at": "Unknown"})
        key = (chunk["document_id"], chunk["page_number"])
        if key not in seen:
            seen.add(key)
            citations.append({
                "document_id": chunk["document_id"],
                "filename": meta["filename"],
                "source_type": chunk["source_type"],
                "page_number": chunk["page_number"]
            })

    return {
        "answer": answer,
        "citations": citations,
        "chunks_used": chunks_used,
        "query_type": q_type,
        "structured_used": structured_used
    }


def run_tests():
    questions = [
        {
            "num": 1,
            "q": "What are the key financial metrics in the report?",
            "desc": "Expected source: text_financial_report.pdf (source_type=text_native)"
        },
        {
            "num": 2,
            "q": "What dates and times are mentioned in the schedule?",
            "desc": "Expected source: photographed_receipt_1.png (timetable schedule, source_type=image)"
        },
        {
            "num": 3,
            "q": "What is the payment method?",
            "desc": "Expected source: photographed_receipt_2.jpeg (source_type=image)"
        }
    ]

    for item in questions:
        print("\n" + "=" * 80)
        print(f"QUESTION {item['num']}: {item['q']}")
        print(f"({item['desc']})")
        print("=" * 80)

        # Retrieve top 5
        print("\n>> RETRIEVING TOP-5 CHUNKS...")
        chunks = retrieve_relevant_chunks(item["q"], top_k=5)
        for i, c in enumerate(chunks):
            print(f"  Match {i+1} (Score: {c['score']:.4f}) | doc={c['document_id'][:8]}... | type={c['source_type']} | page={c['page_number']}")
            print(f"    Text: {c['chunk_text'][:110]}...")

        # Generate answer
        print("\n>> GENERATING ANSWER VIA GROQ...")
        res = generate_answer(item["q"], chunks)

        print("\n[ANSWER]:")
        print(res["answer"])

        print("\n[CITATIONS]:")
        for cit in res["citations"]:
            print(f"  - Document: {cit['document_id']} (Type: {cit['source_type']}, Page/Chunk: {cit['page_number']})")


if __name__ == "__main__":
    run_tests()
