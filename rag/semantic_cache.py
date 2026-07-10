import hashlib
import json
import uuid
import logging
from typing import Optional, Dict, Any

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

from storage.postgres_bronze import SessionLocal, BronzeDocument
from rag.qdrant_store import get_client, QUERY_CACHE_COLLECTION
from rag.retrieval_v2 import _get_model

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.98

def get_tenant_collection_version(tenant_id: str) -> str:
    """
    Generate an MD5 hash of the tenant's current curated documents.
    This guarantees cache invalidation if any document is added, updated, or deleted.
    """
    db = SessionLocal()
    try:
        docs = db.query(BronzeDocument.document_id, BronzeDocument.created_at).filter(
            BronzeDocument.tenant_id == tenant_id,
            BronzeDocument.status == "curated"
        ).order_by(BronzeDocument.document_id).all()
        
        # We stringify the tuples to hash them
        # if no docs, hash is constant
        hash_input = "".join([f"{d[0]}_{d[1]}" for d in docs]).encode('utf-8')
        return hashlib.md5(hash_input).hexdigest()
    finally:
        db.close()

def check_cache(
    query: str, 
    tenant_id: str, 
    prompt_version: str, 
    model_version: str, 
    collection_version: str
) -> Optional[Dict[str, Any]]:
    """
    Checks the semantic cache for a highly similar query.
    Requires exact matches on tenant_id, prompt_version, model_version, and collection_version.
    """
    model = _get_model()
    query_emb = model.encode(query).tolist()
    
    from qdrant_client.http.models import SearchRequest
    client = get_client()
    try:
        res = client.http.search_api.search_points(
            collection_name=QUERY_CACHE_COLLECTION,
            search_request=SearchRequest(
                vector=query_emb,
                filter=Filter(
                    must=[
                        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                        FieldCondition(key="collection_version", match=MatchValue(value=collection_version)),
                        FieldCondition(key="prompt_version", match=MatchValue(value=prompt_version)),
                        FieldCondition(key="model_version", match=MatchValue(value=model_version)),
                    ]
                ),
                limit=1,
                with_payload=True,
                score_threshold=SIMILARITY_THRESHOLD
            )
        )
        hits = res.result
        
        if not hits:
            return None
            
        payload = hits[0].payload
        return {
            "answer": payload.get("answer"),
            "routing_path": payload.get("routing_path", "semantic_cache"),
            "query_type": payload.get("query_type"),
            "confidence": payload.get("confidence", "high"),
            "chunks_used": payload.get("chunks_used", 0),
            "citations": json.loads(payload.get("citations", "[]")),
            "abstained": payload.get("abstained", False),
            "structured_used": payload.get("structured_used", False),
            "structured_query_executed": payload.get("structured_query_executed"),
            "retrieval_meta": json.loads(payload.get("retrieval_meta", "null")),
            "low_confidence_warning": payload.get("low_confidence_warning", False),
            "chunks": json.loads(payload.get("chunks", "[]")),
            "cached_hit": True
        }
        
    except Exception as e:
        logger.error(f"Semantic Cache check failed: {e}")
        return None

def store_in_cache(
    query: str, 
    tenant_id: str, 
    prompt_version: str, 
    model_version: str, 
    collection_version: str,
    result: dict
) -> None:
    """
    Stores a successfully generated RAG response in the semantic cache.
    """
    model = _get_model()
    query_emb = model.encode(query).tolist()
    
    client = get_client()
    point_id = str(uuid.uuid4())
    
    payload = {
        "tenant_id": tenant_id,
        "collection_version": collection_version,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "original_query": query,
        "answer": result.get("answer", ""),
        "routing_path": result.get("routing_path", ""),
        "query_type": result.get("query_type", ""),
        "confidence": result.get("confidence", ""),
        "chunks_used": result.get("chunks_used", 0),
        "citations": json.dumps(result.get("citations", [])),
        "abstained": result.get("abstained", False),
        "structured_used": result.get("structured_used", False),
        "structured_query_executed": result.get("structured_query_executed"),
        "retrieval_meta": json.dumps(result.get("retrieval_meta")),
        "low_confidence_warning": result.get("low_confidence_warning", False),
        "chunks": json.dumps(result.get("chunks", [])),
    }
    
    try:
        client.upsert(
            collection_name=QUERY_CACHE_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=query_emb,
                    payload=payload
                )
            ]
        )
    except Exception as e:
        logger.error(f"Failed to store semantic cache: {e}")
