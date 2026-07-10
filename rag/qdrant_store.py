"""
rag/qdrant_client.py

Qdrant vector store client — self-hosted on localhost:6333.
Handles collection creation and point upsert operations.

Collection: document_chunks
Vector size: 384  (all-MiniLM-L6-v2 output dimension)
Distance:    Cosine

Payload schema per point:
  document_id  : str   — UUID from bronze_documents
  source_type  : str   — "text_native" | "scanned" | "scanned_pdf" | "image"
  page_number  : int   — page index (0-based for OCR, chunk_index for text_native)
  chunk_text   : str   — raw text of this chunk
  file_hash    : str   — SHA-256 of the original file
"""

import os
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

logger = logging.getLogger(__name__)

QDRANT_URL        = os.getenv("QDRANT_URL")
QDRANT_API_KEY    = os.getenv("QDRANT_API_KEY")
QDRANT_HOST       = os.getenv("QDRANT_HOST")
QDRANT_PORT       = os.getenv("QDRANT_PORT")

COLLECTION_NAME   = "document_chunks"
QUERY_CACHE_COLLECTION = "query_cache"
VECTOR_DIMENSION  = 384          # all-MiniLM-L6-v2

# Track connection for one-time startup logging
_connected = False

def get_client() -> QdrantClient:
    """Return a connected Qdrant client."""
    global _connected
    
    if QDRANT_URL:
        client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=30,
            check_compatibility=False
        )
        if not _connected:
            logger.info("[QDRANT] Connected to Qdrant Cloud")
            print("[QDRANT] Connected to Qdrant Cloud")
            _connected = True
        return client
    elif QDRANT_HOST:
        port = int(QDRANT_PORT) if QDRANT_PORT else 6333
        client = QdrantClient(
            host=QDRANT_HOST,
            port=port,
            timeout=30,
            check_compatibility=False
        )
        if not _connected:
            logger.info("[QDRANT] Connected to Local Docker Qdrant")
            print("[QDRANT] Connected to Local Docker Qdrant")
            _connected = True
        return client
    else:
        raise RuntimeError("Qdrant configuration is missing. Must provide QDRANT_URL or QDRANT_HOST.")


def ensure_collection(client: QdrantClient) -> None:
    """
    Create the collections if they do not already exist.
    Idempotent — safe to call on every run.
    """
    existing = [c.name for c in client.get_collections().collections]
    
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")
        
    if QUERY_CACHE_COLLECTION not in existing:
        client.create_collection(
            collection_name=QUERY_CACHE_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {QUERY_CACHE_COLLECTION}")
    else:
        logger.info("Collection already exists: %s", COLLECTION_NAME)


def upsert_chunks(client: QdrantClient, points: list[PointStruct]) -> int:
    """
    Upsert a list of PointStruct objects.
    Returns the number of points successfully upserted.
    """
    if not points:
        return 0

    # Qdrant recommends batches of ≤ 100 for reliability
    BATCH_SIZE = 100
    total = 0
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        total += len(batch)

    return total


def get_point_count(client: QdrantClient) -> int:
    """Return the total number of points in the collection."""
    info = client.get_collection(COLLECTION_NAME)
    return info.points_count


def query_by_payload(
    client: QdrantClient,
    field: str,
    value: str,
    limit: int = 5,
) -> list[dict]:
    """
    Scroll through the collection and return up to `limit` points
    where payload[field] == value.  Used for verification.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key=field, match=MatchValue(value=value))]
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [{"id": str(r.id), "payload": r.payload} for r in results]
