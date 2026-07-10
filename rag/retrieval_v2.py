"""
rag/retrieval_v2.py

Redesigned retrieval engine addressing Root Cause A:
- Dynamic top_k based on query classification
- Confidence threshold filtering (per query type)
- Exact-duplicate deduplication
- Re-ranking by score (descending)
- chunk_type detection (table / list / prose)
- low_confidence flagging when < 3 chunks survive

Usage:
    from rag.retrieval_v2 import retrieve_with_confidence, ChunkWithContext
"""

import os
import re
import sys
from dataclasses import dataclass, field

from sentence_transformers import SentenceTransformer

import rag.qdrant_store as qc
from rag.query_classifier import classify_query

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME = "all-MiniLM-L6-v2"

# Confidence thresholds per query type (lowered to accommodate all-MiniLM-L6-v2 raw scores)
# Confidence thresholds per query type (lowered to accommodate all-MiniLM-L6-v2 raw scores)
CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "aggregation":  0.0,   # Aggregation needs all chunks it can get
    "comparison":   0.10,
    "table_lookup": 0.10,
    "descriptive":  0.10,
    "synthesis":    0.0,   # No threshold for synthesis, we want all docs
}

# Top-K limits per query type (reduced to prevent Groq 6000 TPM Rate Limit)
TOP_K_MAP: dict[str, int] = {
    "aggregation":  25,    # Increased to allow accurate document-wide counting
    "comparison":   10,
    "table_lookup": 10,
    "descriptive":  10,
    "synthesis":    15,
}

LOW_CONFIDENCE_CHUNK_FLOOR = 3  # fewer than this → set low_confidence flag

# ── Model singleton ────────────────────────────────────────────────────────────
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def preload_model():
    """Eagerly load the SentenceTransformer model to avoid cold-start penalties."""
    global _model
    if _model is None:
        import logging
        logging.getLogger(__name__).info(f"Preloading embedding model {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)


# ── Data model ─────────────────────────────────────────────────────────────────
@dataclass
class ChunkWithContext:
    chunk_text: str
    document_id: str
    page_number: int
    confidence_score: float
    chunk_type: str          # "table" | "list" | "prose"
    chunk_rank: int          # 1-indexed, 1 = most relevant
    query_type_used: str
    source_type: str
    tenant_id: str = ""

    def to_dict(self) -> dict:
        return {
            "chunk_text":       self.chunk_text,
            "document_id":      self.document_id,
            "page_number":      self.page_number,
            "confidence_score": self.confidence_score,
            "chunk_type":       self.chunk_type,
            "chunk_rank":       self.chunk_rank,
            "query_type_used":  self.query_type_used,
            "source_type":      self.source_type,
            "tenant_id":        self.tenant_id,
            "score":            self.confidence_score,  # backward-compat alias
        }


# ── Chunk type detection ───────────────────────────────────────────────────────
def _detect_chunk_type(text: str) -> str:
    """
    Heuristically classify a chunk as 'table', 'list', or 'prose'.

    table: ≥ 3 lines containing '|' OR average spaces-per-line > 8 (grid layout)
    list:  ≥ 3 lines starting with a bullet/number marker
    prose: everything else
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return "prose"

    pipe_lines = sum(1 for l in lines if "|" in l)
    if pipe_lines >= 3:
        return "table"

    # Detect grid-like alignment (lots of whitespace columns)
    avg_spaces = sum(len(re.findall(r"  +", l)) for l in lines) / len(lines)
    if avg_spaces >= 2 and len(lines) >= 3:
        return "table"

    list_pattern = re.compile(r"^\s*(?:[-*•]|\d+[.):])\s+")
    list_lines = sum(1 for l in lines if list_pattern.match(l))
    if list_lines >= 3:
        return "list"

    return "prose"


# ── Core retrieval function ────────────────────────────────────────────────────
def retrieve_with_confidence(
    query: str,
    tenant_id: str | None = None,
) -> tuple[list[ChunkWithContext], dict]:
    """
    Retrieve document chunks from Qdrant with confidence gating and re-ranking.

    Returns
    -------
    chunks : list[ChunkWithContext]  (empty list if nothing passes threshold)
    meta   : dict with keys:
        query_type       str
        low_confidence   bool
        threshold_used   float
        top_k_used       int
        total_fetched    int
        total_after_filter int
    """
    client = qc.get_client()
    qc.ensure_collection(client)
    model = _get_model()

    # Step 1: Classify query
    classification = classify_query(query)
    q_type = classification["type"]
    preferred_purpose = classification.get("preferred_purpose")
    
    threshold = CONFIDENCE_THRESHOLDS.get(q_type, 0.20)
    
    # Lower threshold dynamically for receipts/financial if descriptive
    if preferred_purpose == "Financial" and q_type == "descriptive":
        threshold = 0.10
        
    top_k = TOP_K_MAP.get(q_type, 15)

    # Step 2: Embed query
    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    # Step 3: Build Qdrant filter
    from qdrant_client.http.models import (
        SearchRequest, Filter, FieldCondition, MatchValue, MatchExcept
    )

    must_conditions = []
    if tenant_id:
        must_conditions.append(
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
        )

    # Source-type routing (inherited from v1 keyword routing)
    # ONLY apply if not a synthesis query (synthesis must search all docs)
    if q_type != "synthesis":
        q_lower = query.lower()
        csv_keywords = ["csv", "table", "sheet", "row", "col", "excel", "spreadsheet"]
        pdf_keywords = [
            "pdf", "document", "file", "page", "invoice", "receipt",
            "syllabus", "report", "text", "email", "mail", "letter",
            "venue", "instructions",
        ]
        if any(w in q_lower for w in csv_keywords):
            must_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value="csv"))
            )
        elif any(w in q_lower for w in pdf_keywords):
            must_conditions.append(
                FieldCondition(
                    key="source_type",
                    match=MatchExcept(**{"except": ["csv"]})
                )
            )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    # Step 4: Query Qdrant
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
    total_fetched = len(hits)

    # Step 5: Confidence filtering
    filtered = []
    for hit in hits:
        score = getattr(hit, "score", 0.0)
        if score >= threshold:
            filtered.append((hit, score))

    total_after_filter = len(filtered)
    low_confidence = total_after_filter < LOW_CONFIDENCE_CHUNK_FLOOR

    # Step 6: Deduplication (exact chunk_text match)
    seen_texts: set[str] = set()
    deduped = []
    for hit, score in filtered:
        payload = hit.payload or {}
        text = (payload.get("chunk_text") or "").strip()
        if text and text not in seen_texts:
            seen_texts.add(text)
            deduped.append((hit, score))

    # Step 7: Re-rank by score descending, with purpose boosting and diversity
    # Boost by preferred purpose
    if preferred_purpose:
        boosted = []
        for hit, score in deduped:
            payload = hit.payload or {}
            if payload.get("document_purpose") == preferred_purpose:
                score += 0.10
            boosted.append((hit, score))
        deduped = boosted
        
    deduped.sort(key=lambda x: x[1], reverse=True)
    
    # Interleave chunks by document for synthesis queries
    if q_type == "synthesis" and deduped:
        from collections import defaultdict
        docs_dict = defaultdict(list)
        for hit, score in deduped:
            doc_id = (hit.payload or {}).get("document_id", "unknown")
            docs_dict[doc_id].append((hit, score))
        
        interleaved = []
        # Continue popping from each document's list until all are empty
        while docs_dict:
            to_remove = []
            for doc_id, items in docs_dict.items():
                if items:
                    interleaved.append(items.pop(0))
                if not items:
                    to_remove.append(doc_id)
            for doc_id in to_remove:
                del docs_dict[doc_id]
        
        deduped = interleaved

    # Step 8: Build ChunkWithContext objects
    chunks: list[ChunkWithContext] = []
    for rank, (hit, score) in enumerate(deduped, start=1):
        payload = hit.payload or {}
        text = (payload.get("chunk_text") or "").strip()
        chunks.append(ChunkWithContext(
            chunk_text=text,
            document_id=payload.get("document_id", ""),
            page_number=payload.get("page_number", 0),
            confidence_score=round(score, 4),
            chunk_type=_detect_chunk_type(text),
            chunk_rank=rank,
            query_type_used=q_type,
            source_type=payload.get("source_type", ""),
            tenant_id=payload.get("tenant_id", tenant_id or ""),
        ))

    meta = {
        "query_type":         q_type,
        "low_confidence":     low_confidence,
        "threshold_used":     threshold,
        "top_k_used":         top_k,
        "total_fetched":      total_fetched,
        "total_after_filter": total_after_filter,
    }

    return chunks, meta



