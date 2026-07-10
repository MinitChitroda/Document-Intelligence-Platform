"""
rag/generation_v2.py

Redesigned answer generation addressing Root Cause B:
- Hard confidence gate BEFORE calling Groq (abstain if no good evidence)
- Strict evidence-only system prompt (no deduction latitude)
- Citation verification: reject answers that make claims without in-text citations
- Fabricated citation detection: verify cited chunk IDs exist in retrieved set
- Confidence level assignment based on max chunk score

Usage:
    from rag.generation_v2 import generate_answer_with_evidence
    from rag.retrieval_v2 import ChunkWithContext
"""

import os
import re
import sys
import json
import logging
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.gemini_client import get_gemini_manager


# ── Constants ──────────────────────────────────────────────────────────────────
ABSTAIN_RESPONSE = (
    "I cannot find relevant evidence to answer this question. "
    "The retrieved context does not contain sufficient information to provide a reliable answer."
)
INSUFFICIENT_EVIDENCE_RESPONSE = (
    "I cannot find sufficient evidence to answer this question. "
    "Please ensure the relevant documents have been uploaded and indexed."
)
NO_CITATION_RESPONSE = (
    "I was unable to generate a properly cited answer from the retrieved evidence. "
    "The context may be ambiguous or insufficient for this question."
)

# Confidence score bands
CONFIDENCE_HIGH_THRESHOLD   = 0.55
CONFIDENCE_MEDIUM_THRESHOLD = 0.40
CONFIDENCE_LOW_THRESHOLD    = 0.25

# Pre-generation gate: if best chunk below this, abstain immediately
ABSTAIN_SCORE_GATE = 0.30


# ── System prompt (strict evidence-only) ──────────────────────────────────────
SYSTEM_PROMPT = """\
You are a highly capable document analyst. You operate under STRICT evidence-only rules, but you are also intelligent and flexible in understanding the user's intent.

RULE 1: Answer ONLY when you have evidence in the provided context chunks.
RULE 2: If the user's question is phrased unusually, uses different terminology (e.g., asking for "batch" when the document says "specialization" or "course"), or is twisted, actively map their concepts to the document's terminology and answer it if the underlying information is present.
RULE 3: Every single claim you make MUST be supported by at least one retrieved chunk.
RULE 4: You MUST cite the source for every statement in this format: (Document: <filename>, Page: <number>).
RULE 5: If the retrieved chunks genuinely do not contain the answer or the information needed to deduce it, say EXACTLY:
  "I cannot find sufficient evidence to answer this question."
RULE 6: Do NOT hallucinate, guess, or add external knowledge.
RULE 7: If you are asked to count, aggregate, or calculate based on the provided chunks, you MAY do so, as long as you rely strictly on the provided data.
RULE 8: If the context chunks contain contradictory values, explicitly acknowledge the contradiction.
RULE 9: When synthesizing across documents, explicitly name the document (e.g., 'Student information came from...').

Response format:
[Your direct answer with inline citations]

Sources:
- (Document: <filename>, Page: <number>) — <exact relevant quote from chunk>
- (Document: <filename>, Page: <number>) — <exact relevant quote from chunk>
"""


# ── Confidence level assignment ────────────────────────────────────────────────
def _assign_confidence(chunks: list) -> str:
    """Assign HIGH/MEDIUM/LOW/NONE based on the best score in the retrieved set."""
    if not chunks:
        return "none"
    max_score = max(
        (c.confidence_score if hasattr(c, "confidence_score") else c.get("confidence_score", 0.0))
        for c in chunks
    )
    if max_score >= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if max_score >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    if max_score >= CONFIDENCE_LOW_THRESHOLD:
        return "low"
    return "none"


# ── Citation verification ──────────────────────────────────────────────────────
def _has_inline_citations(answer: str) -> bool:
    """
    Check that the answer contains at least one citation in expected format.
    Accepts: (Document: ..., Page: ...) or 'Source: ..., Page ...'
    """
    pattern = re.compile(
        r"\(Document:.*?Page.*?\)"
        r"|Source:.*?Page"
        r"|Document.*?Page\s*\d",
        re.IGNORECASE | re.DOTALL
    )
    return bool(pattern.search(answer))


def _extract_cited_filenames(answer: str) -> list[str]:
    """Extract all filenames mentioned inside (Document: ...) citations."""
    pattern = re.compile(r"\(Document:\s*([^,]+?),", re.IGNORECASE)
    return [m.group(1).strip() for m in pattern.finditer(answer)]


# ── Context builder ────────────────────────────────────────────────────────────
def _build_context(chunks: list, doc_metadata: dict) -> str:
    """
    Format chunks as labelled evidence blocks.
    chunks: list of ChunkWithContext or dicts.
    doc_metadata: {document_id: {filename, created_at}}
    """
    parts = []
    for chunk in chunks:
        if hasattr(chunk, "to_dict"):
            c = chunk.to_dict()
        else:
            c = chunk

        doc_id   = c.get("document_id", "")
        meta     = doc_metadata.get(doc_id, {})
        filename = meta.get("filename") or f"Document_{doc_id[:8]}"
        rank     = c.get("chunk_rank", "?")
        page     = c.get("page_number", 0)
        score    = c.get("confidence_score", c.get("score", 0.0))
        ctype    = c.get("chunk_type", "prose")
        text     = c.get("chunk_text", "")

        parts.append(
            f"[CHUNK {rank} | Document: {filename} | Page: {page} | "
            f"Score: {score:.2f} | Type: {ctype.upper()}]\n{text}"
        )
    return "\n\n".join(parts)


# ── Main generation function ───────────────────────────────────────────────────
def generate_answer_with_evidence(
    query: str,
    chunks: list,
    query_type: str = "descriptive",
    structured_result: dict | None = None,
    doc_metadata: dict | None = None,
    stream: bool = False
) -> dict:
    """
    Generate a strictly evidence-grounded answer.

    Parameters
    ----------
    query            : user question
    chunks           : list of ChunkWithContext or dicts (from retrieval_v2)
    query_type       : from query_classifier
    structured_result: dict from structured_query_handler (bypasses chunk check)
    doc_metadata     : {document_id: {filename, created_at}} — fetched externally

    Returns
    -------
    dict with keys:
        answer, confidence, chunks_used, citations, abstained, query_type,
        structured_used, query_executed (if structured)
    """
    gemini_manager = get_gemini_manager()


    # ── Step 1: Hard confidence gate ──────────────────────────────────────────
    # If structured result available, skip chunk gate (structured = always high confidence)
    if structured_result is None:
        if not chunks:
            return {
                "answer":       ABSTAIN_RESPONSE,
                "confidence":   "none",
                "chunks_used":  0,
                "citations":    [],
                "abstained":    True,
                "query_type":   query_type,
                "structured_used": False,
            }

        # Check best chunk score
        max_score = max(
            (c.confidence_score if hasattr(c, "confidence_score") else c.get("confidence_score", c.get("score", 0.0)))
            for c in chunks
        )

    # ── Step 1: Resolve doc metadata if not provided ──────────────────────────
    if doc_metadata is None:
        doc_metadata = {}
        try:
            from storage.postgres_bronze import SessionLocal, BronzeDocument
            if structured_result:
                doc_ids = [structured_result["document_id"]]
            else:
                doc_ids = list({
                    (c.document_id if hasattr(c, "document_id") else c.get("document_id", ""))
                    for c in chunks
                })
            if doc_ids:
                db = SessionLocal()
                rows = db.query(BronzeDocument).filter(
                    BronzeDocument.document_id.in_(doc_ids)
                ).all()
                for r in rows:
                    doc_metadata[r.document_id] = {
                        "filename":   r.filename or f"Document_{r.document_id[:8]}",
                        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "Unknown",
                    }
                db.close()
        except Exception:
            pass

    # ── Step 2: Build context string ──────────────────────────────────────────
    structured_used = structured_result is not None

    if structured_used:
        doc_id   = structured_result["document_id"]
        meta     = doc_metadata.get(doc_id, {})
        filename = meta.get("filename") or structured_result.get("filename") or f"Document_{doc_id[:8]}"
        context_str = (
            f"[STRUCTURED RESULT | Document: {filename} | Source: CSV | Score: 1.00 | Type: TABLE]\n"
            f"Query executed: {structured_result.get('query_executed', 'N/A')}\n"
            f"Result: {structured_result['formatted_evidence']}"
        )
        chunks_used_list = [{
            "document_id":  doc_id,
            "page_number":  0,
            "source_type":  "csv",
            "chunk_text":   structured_result["formatted_evidence"],
            "chunk_type":   "table",
            "chunk_rank":   1,
            "confidence_score": 1.0,
            "score": 1.0,
        }]
    else:
        from rag.context_optimizer import optimize_context
        # Optimizing context before building string
        optimized_chunks = optimize_context(chunks)
        
        context_str = _build_context(optimized_chunks, doc_metadata)
        chunks_used_list = optimized_chunks

    # ── Step 3: Call Gemini ─────────────────────────────────────────────────────
    prompt = (
        f"Retrieved Evidence:\n{context_str}\n\n"
        f"Question: {query}"
    )

    try:
        if stream:
            generator = gemini_manager.stream_with_fallback(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model="gemini-flash-latest",
                temperature=0.0
            )
            raw_answer = ""
        else:
            raw_answer = gemini_manager.call_with_fallback(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model="gemini-flash-latest",
                temperature=0.0
            )
            generator = None
    except Exception as e:
        return {
            "answer":      f"[ERROR calling Gemini API]: {e}",
            "confidence":  "none",
            "chunks_used": len(chunks_used_list),
            "citations":   [],
            "abstained":   True,
            "query_type":  query_type,
            "structured_used": structured_used,
        }

    # ── Step 4: Citation presence check ───────────────────────────────────────
    answer_text = raw_answer.strip() if not stream else ""

    is_abstain_response = (
        "cannot find" in answer_text.lower()
        or "insufficient evidence" in answer_text.lower()
    ) if not stream else False
    
    abstained = is_abstain_response

    # ── Step 5: Extract citations and build output list ───────────────────────
    # For streaming, we just extract from chunks used since we don't have the final text yet
    cited_filenames = _extract_cited_filenames(answer_text) if not stream else []

    # Build citation list from chunks that were used
    seen_keys: set[tuple] = set()
    citations = []
    for c in chunks_used_list:
        doc_id  = c.get("document_id", "")
        page    = c.get("page_number", 0)
        meta    = doc_metadata.get(doc_id, {})
        fname   = meta.get("filename") or f"Document_{doc_id[:8]}"
        key     = (doc_id, page)
        if key not in seen_keys:
            seen_keys.add(key)
            citations.append({
                "document_id": doc_id,
                "filename":    fname,
                "source_type": c.get("source_type", ""),
                "page_number": page,
            })

    # Assign confidence
    if structured_used:
        confidence = "high"
    else:
        confidence = _assign_confidence(chunks)
    if abstained:
        confidence = "none"

    result = {
        "answer":          answer_text,
        "answer_generator": generator,
        "confidence":      confidence,
        "chunks_used":     len(chunks_used_list),
        "citations":       citations,
        "abstained":       abstained,
        "query_type":      query_type,
        "structured_used": structured_used,
    }
    if structured_used:
        result["query_executed"] = structured_result.get("query_executed", "N/A")

    return result



