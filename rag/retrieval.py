"""
rag/retrieval.py

Retrieves the top-K most similar document chunks from Qdrant given a query.
"""

import os
from sentence_transformers import SentenceTransformer
import rag.qdrant_store as qc

# Initialize the embedding model (cached/fast once loaded)
MODEL_NAME = "all-MiniLM-L6-v2"
model = None


def get_model() -> SentenceTransformer:
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model


from rag.query_classifier import classify_query

def retrieve_relevant_chunks(query: str, tenant_id: str = None, top_k: int = None) -> list[dict]:
    """
    Embed the user query and search Qdrant for top-K matches.
    Determines top_k dynamically based on query classification if not specified.
    Filters out any results with a similarity score < 0.4.
    """
    client = qc.get_client()
    embedding_model = get_model()

    # Determine dynamic top_k based on query type
    classification = classify_query(query)
    q_type = classification["type"]
    
    if top_k is None:
        if q_type == "aggregation":
            top_k = 100
        elif q_type == "comparison":
            top_k = 30
        elif q_type == "table_lookup":
            top_k = 20
        else:
            top_k = 15

    # Generate query embedding
    query_vector = embedding_model.encode(query, normalize_embeddings=True).tolist()

    from qdrant_client.http.models import SearchRequest, Filter, FieldCondition, MatchValue, MatchExcept

    # Source-aware target routing based on query keywords
    target_source = None
    q_lower = query.lower()
    if any(w in q_lower for w in ["csv", "table", "sheet", "row", "col", "excel"]):
        target_source = "csv"
    elif any(w in q_lower for w in ["pdf", "document", "file", "page", "invoice", "receipt", "syllabus", "report", "text", "email", "mail", "letter", "venue", "instructions"]):
        target_source = "non_csv"

    must_conditions = []
    if tenant_id:
        must_conditions.append(FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)))
    
    if target_source == "csv":
        must_conditions.append(FieldCondition(key="source_type", match=MatchValue(value="csv")))
    elif target_source == "non_csv":
        must_conditions.append(FieldCondition(key="source_type", match=MatchExcept(**{"except": ["csv"]})))

    query_filter = Filter(must=must_conditions) if must_conditions else None

    # Query Qdrant using the REST search API for compatibility with server v1.9.2
    res = client.http.search_api.search_points(
        collection_name=qc.COLLECTION_NAME,
        search_request=SearchRequest(
            vector=query_vector,
            limit=top_k,
            filter=query_filter,
            with_payload=True,
        )
    )
    hits = res.result

    results = []
    for hit in hits:
        payload = hit.payload or {}
        score = getattr(hit, "score", 1.0)
        
        # Filter by relevance: score >= 0.10 for descriptive queries, >= 0.30 for other query types
        threshold = 0.10 if q_type == "descriptive" else 0.30
        if score < threshold:
            continue
            
        results.append({
            "id": hit.id,
            "score": score,
            "document_id": payload.get("document_id"),
            "tenant_id": payload.get("tenant_id"),
            "source_type": payload.get("source_type"),
            "page_number": payload.get("page_number"),
            "chunk_text": payload.get("chunk_text"),
        })

    return results



if __name__ == "__main__":
    # Small test
    query = "What is the payment method?"
    print(f"Testing retrieval for query: '{query}'")
    chunks = retrieve_relevant_chunks(query, top_k=5)
    for i, c in enumerate(chunks):
        print(f"\nMatch {i+1} (Score: {c['score']:.4f}):")
        print(f"  doc_id: {c['document_id']}")
        print(f"  source_type: {c['source_type']}")
        print(f"  page_number: {c['page_number']}")
        print(f"  text: {c['chunk_text'][:120]}...")
