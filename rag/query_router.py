"""
rag/query_router.py

Unified query routing entry point — Phase 5.

Routes every incoming query through:
  1. Query classification
  2. Structured path (CSV Pandas handler) if applicable
  3. Semantic path (retrieval_v2 + generation_v2) as fallback

Usage:
    from rag.query_router import route_query
    result = route_query(query="How many students in IT?", tenant_id="tenant_1")
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.query_classifier import classify_query
from rag.retrieval_v2 import retrieve_with_confidence
from rag.generation_v2 import generate_answer_with_evidence, SYSTEM_PROMPT
from rag.structured_query_handler import handle_structured_query
from rag.semantic_cache import check_cache, store_in_cache, get_tenant_collection_version
import hashlib


STRUCTURED_PREFERRED_TYPES = {"aggregation", "table_lookup", "comparison"}


def route_query(query: str, tenant_id: str, status_callback=None, stream: bool = False) -> dict:
    """
    Route a query through the optimal path and return a unified result.

    Decision logic:
    ┌─────────────────────────────────────────────────────────┐
    │ 1. Classify query                                        │
    │ 2. Try structured handler (CSV) for ALL query types      │
    │    └─ If returns None → fall to semantic                 │
    │ 3. Semantic: retrieve_with_confidence + generation_v2    │
    └─────────────────────────────────────────────────────────┘

    Parameters
    ----------
    query            : user question
    tenant_id        : tenant scope
    status_callback  : optional callable receiving string updates for RAG steps
    stream           : whether to stream the generation

    Returns
    -------
    dict with keys:
        answer                 str
        answer_generator       generator | None
        routing_path           "structured" | "semantic"
        query_type             str
        confidence             "high" | "medium" | "low" | "none"
        chunks_used            int
        citations              list[dict]
        abstained              bool
        structured_used        bool
        structured_query_executed  str | None   (the Pandas code, if structured)
        retrieval_meta         dict | None      (retrieval stats, if semantic)
        low_confidence_warning bool             (True if < 3 chunks survived filter)
    """

    if status_callback:
        status_callback("Checking semantic cache...")

    try:
        collection_version = get_tenant_collection_version(tenant_id)
        prompt_version = hashlib.md5(SYSTEM_PROMPT.encode()).hexdigest()
        model_version = "gemini-flash-latest"

        cached_result = check_cache(
            query=query,
            tenant_id=tenant_id,
            prompt_version=prompt_version,
            model_version=model_version,
            collection_version=collection_version
        )

        if cached_result:
            if status_callback:
                status_callback("Cache hit! Returning instant response...")
            if stream:
                def dummy_gen():
                    yield cached_result["answer"]
                cached_result["answer_generator"] = dummy_gen()
            else:
                cached_result["answer_generator"] = None
            return cached_result
    except Exception as e:
        print(f"[CACHE CHECK ERROR] {e}")
        # On error, fallback to normal execution
        collection_version = "unknown"
        prompt_version = "unknown"
        model_version = "unknown"

    if status_callback:
        status_callback("Classifying query intent...")

    classification = classify_query(query)
    q_type = classification["type"]
    preferred_purpose = classification.get("preferred_purpose")

    # ── Step 2: Try structured handler first ──────────────────────────────────
    structured_result = None
    routing_path = "semantic"  # default

    # Only try structured if it's an aggregation/table/comparison, OR if it's Academic.
    # Do NOT try structured for Financial or Recruitment queries if they are just descriptive.
    should_try_structured = q_type in STRUCTURED_PREFERRED_TYPES
    if q_type == "descriptive" and preferred_purpose in ("Financial", "Recruitment"):
        should_try_structured = False

    if should_try_structured:
        if status_callback:
            status_callback("Attempting structured data query...")
        try:
            structured_result = handle_structured_query(
                query=query,
                tenant_id=tenant_id,
                q_type=q_type,
            )
        except Exception as e:
            print(f"[ROUTER] Structured handler error (falling back): {e}")
            structured_result = None

    if structured_result is not None:
        if status_callback:
            status_callback("Generating answer from structured result...")
        # Use structured result → pass to generation_v2 as evidence
        routing_path = "structured"
        gen_result = generate_answer_with_evidence(
            query=query,
            chunks=[],
            query_type=q_type,
            structured_result=structured_result,
            stream=stream
        )
        final_result = {
            "answer":                    gen_result.get("answer", ""),
            "answer_generator":          gen_result.get("answer_generator"),
            "routing_path":              routing_path,
            "query_type":                q_type,
            "confidence":                gen_result["confidence"],
            "chunks_used":               gen_result["chunks_used"],
            "citations":                 gen_result["citations"],
            "abstained":                 gen_result["abstained"],
            "structured_used":           True,
            "structured_query_executed": structured_result.get("query_executed"),
            "retrieval_meta":            None,
            "low_confidence_warning":    False,
        }
    else:
        # ── Step 3: Semantic retrieval + generation ───────────────────────────────
        routing_path = "semantic"

        if status_callback:
            status_callback("Searching Qdrant vector database...")

        chunks, retrieval_meta = retrieve_with_confidence(
            query=query,
            tenant_id=tenant_id,
        )

        low_confidence_warning = retrieval_meta.get("low_confidence", False)

        if status_callback:
            status_callback(f"Analyzing {len(chunks)} chunks & synthesizing answer (Gemini)...")

        gen_result = generate_answer_with_evidence(
            query=query,
            chunks=chunks,
            query_type=q_type,
            structured_result=None,
            stream=stream
        )

        final_result = {
            "answer":                    gen_result.get("answer", ""),
            "answer_generator":          gen_result.get("answer_generator"),
            "routing_path":              routing_path,
            "query_type":                q_type,
            "confidence":                gen_result["confidence"],
            "chunks_used":               gen_result["chunks_used"],
            "citations":                 gen_result["citations"],
            "abstained":                 gen_result["abstained"],
            "structured_used":           False,
            "structured_query_executed": None,
            "retrieval_meta":            retrieval_meta,
            "low_confidence_warning":    low_confidence_warning,
            # Pass through chunks for dashboard display
            "chunks": [(c.to_dict() if hasattr(c, "to_dict") else c) for c in chunks],
        }

    # Cache storing logic
    if stream and final_result.get("answer_generator"):
        def cache_wrapping_generator(gen, res_dict):
            full_text = ""
            for token in gen:
                full_text += token
                yield token
            
            res_dict["answer"] = full_text
            try:
                store_in_cache(
                    query=query,
                    tenant_id=tenant_id,
                    prompt_version=prompt_version,
                    model_version=model_version,
                    collection_version=collection_version,
                    result=res_dict
                )
            except Exception as e:
                print(f"[CACHE ERROR] {e}")

        final_result["answer_generator"] = cache_wrapping_generator(final_result["answer_generator"], final_result.copy())
    else:
        try:
            store_in_cache(
                query=query,
                tenant_id=tenant_id,
                prompt_version=prompt_version,
                model_version=model_version,
                collection_version=collection_version,
                result=final_result
            )
        except Exception as e:
            print(f"[CACHE ERROR] {e}")

    return final_result



