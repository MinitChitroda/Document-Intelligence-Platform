"""
evaluation/evaluate_retrieval.py

Evaluates RAG retrieval precision, confidence, and difficulty breakdown.
Performs failure analysis for misses.
"""

import os
import sys
import json
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.retrieval import retrieve_relevant_chunks
from rag.generation import generate_answer

QUERIES_FILE = "evaluation/test_queries.json"
FAILURES_FILE = "evaluation/failures.md"
METRICS_FILE = "metrics.md"


def run_evaluation():
    if not os.path.exists(QUERIES_FILE):
        print(f"[ERROR] test_queries.json not found. Run setup_evaluation.py first.")
        sys.exit(1)

    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        queries = json.load(f)

    print(f"Loaded {len(queries)} evaluation test queries.")

    # Counters
    total = len(queries)
    overall_hits = 0
    
    source_stats = {
        "text_native": {"total": 0, "hits": 0},
        "scanned_pdf": {"total": 0, "hits": 0},
        "image": {"total": 0, "hits": 0}
    }
    
    diff_stats = {
        "easy": {"total": 0, "hits": 0},
        "medium": {"total": 0, "hits": 0},
        "hard": {"total": 0, "hits": 0}
    }

    total_similarity_score = 0.0
    total_chunks_retrieved = 0
    low_confidence_queries = 0

    failures = []

    # Reset failures file
    with open(FAILURES_FILE, "w", encoding="utf-8") as f:
        f.write("# RAG Retrieval Failure Analysis\n\n")
        f.write(f"Generated on: {date.today()}\n\n")
        f.write("| Question | Expected ID | Top Retrieved ID | Top Score | Reason |\n")
        f.write("|---|---|---|---|---|\n")

    for q in queries:
        question = q["question"]
        expected_id = q["expected_document_id"]
        source_type = q["expected_source_type"]
        difficulty = q["difficulty"]

        # Track category counts
        source_stats[source_type]["total"] += 1
        diff_stats[difficulty]["total"] += 1

        # Retrieve chunks
        chunks = retrieve_relevant_chunks(question, top_k=5)

        # Check for hit
        hit = False
        top_retrieved_id = None
        top_score = 0.0

        if chunks:
            top_retrieved_id = chunks[0]["document_id"]
            top_score = chunks[0]["score"]

            # Calculate average score of retrieved chunks for confidence
            avg_query_score = sum(c["score"] for c in chunks) / len(chunks)
            total_similarity_score += avg_query_score
            total_chunks_retrieved += 1
            if avg_query_score < 0.1:
                low_confidence_queries += 1

            for chunk in chunks:
                if chunk["document_id"] == expected_id:
                    hit = True
                    break
        else:
            # Handle empty chunks scenario
            avg_query_score = 0.0
            low_confidence_queries += 1

        if hit:
            overall_hits += 1
            source_stats[source_type]["hits"] += 1
            diff_stats[difficulty]["hits"] += 1
        else:
            # Print MISS to console
            print(f"MISS: Q={question} | Expected={expected_id} | Retrieved={top_retrieved_id} | Score={top_score:.4f}")
            
            # Formulate failure reasoning
            reason = "Weak match/Low semantic score"
            if top_score < 0.1:
                reason = "Low retrieval confidence (possible OCR degradation or query mismatch)"
            elif source_type == "image":
                reason = "Complex image text layouts or OCR noise"
            elif difficulty == "hard":
                reason = "Hard reasoning query requires cross-chunk linking"

            failures.append({
                "question": question,
                "expected_id": expected_id,
                "retrieved_id": top_retrieved_id,
                "score": top_score,
                "reason": reason
            })

            # Append to failures.md
            with open(FAILURES_FILE, "a", encoding="utf-8") as f:
                f.write(f"| {question} | `{expected_id}` | `{top_retrieved_id}` | {top_score:.4f} | {reason} |\n")

    # Math
    overall_precision = (overall_hits / total) * 100 if total > 0 else 0.0
    avg_confidence = total_similarity_score / total_chunks_retrieved if total_chunks_retrieved > 0 else 0.0

    # Print Summary Table
    print("\n============================================================")
    print("EVALUATION RESULTS")
    print("============================================================")
    print(f"Total Questions: {total}")
    print(f"Overall Precision@5: {overall_precision:.1f}%")
    
    print("\nBy Source Type:")
    for st, stats in source_stats.items():
        prec = (stats["hits"] / stats["total"]) * 100 if stats["total"] > 0 else 0.0
        print(f"  {st:<15}: {prec:.1f}% ({stats['hits']}/{stats['total']} hit)")
        
    print("\nBy Difficulty:")
    for df, stats in diff_stats.items():
        prec = (stats["hits"] / stats["total"]) * 100 if stats["total"] > 0 else 0.0
        print(f"  {df:<15}: {prec:.1f}% ({stats['hits']}/{stats['total']} hit)")

    print("\nRetrieval Confidence:")
    print(f"  Avg score      : {avg_confidence:.2f}")
    if low_confidence_queries > 0:
        print(f"  Low conf (<0.1): {low_confidence_queries} queries had low confidence retrievals — answers may be unreliable")
    else:
        print(f"  Low conf (<0.1): {low_confidence_queries} queries")

    print(f"\nFailures: See {FAILURES_FILE}")
    print("============================================================\n")

    # Format source type percentages for metrics file
    st_prec = {}
    for st, stats in source_stats.items():
        st_prec[st] = (stats["hits"] / stats["total"]) * 100 if stats["total"] > 0 else 0.0

    # Append to metrics.md
    metrics_row = (
        f"| {date.today()} | Week 5 Prompt 17 | RAG Evaluation | Precision@5 | "
        f"Overall: {overall_precision:.1f}% | text_native: {st_prec['text_native']:.1f}% | "
        f"scanned_pdf: {st_prec['scanned_pdf']:.1f}% | image: {st_prec['image']:.1f}% | "
        f"[{total} questions, {len(failures)} failures, avg confidence: {avg_confidence:.3f}] |\n"
    )
    
    with open(METRICS_FILE, "a", encoding="utf-8") as f:
        f.write(metrics_row)
    print(f"Metrics appended to {METRICS_FILE}")


if __name__ == "__main__":
    run_evaluation()
