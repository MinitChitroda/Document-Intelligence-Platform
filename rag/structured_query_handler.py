"""
rag/structured_query_handler.py

Redesigned structured data handler addressing Root Cause C:
- Handles ALL query types for CSV documents (not just 'aggregation')
- LLM-generated Pandas expressions with safety sandboxing
- Header-aware CSV selection (best match per query)
- Graceful fallback to None on any failure

Usage:
    from rag.structured_query_handler import handle_structured_query
    result = handle_structured_query(query="How many students in IT?", tenant_id="tenant_1")
"""

import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag.groq_client import get_groq_manager
from rag.query_classifier import classify_query

# ── Safety gate: forbidden tokens in LLM-generated code ───────────────────────
FORBIDDEN_CODE_TOKENS = [
    "import", "__", "open(", "os.", "sys.", "exec(", "eval(",
    "subprocess", "shutil", "pathlib", "globals(", "locals(",
    "compile(", "getattr(", "setattr(", "delattr(",
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
]


def _is_safe_code(code: str) -> bool:
    """Return True only if the generated code passes the safety filter."""
    for token in FORBIDDEN_CODE_TOKENS:
        if token in code:
            return False
    return True


# ── CSV selection helper ───────────────────────────────────────────────────────
def _resolve_raw_path(file_hash: str) -> str | None:
    """Find a physical file in data/raw/ by file_hash prefix."""
    # Check tenant subfolder first
    parts = file_hash.rsplit("_", 1)
    if len(parts) == 2:
        tenant_id = parts[0]
        tenant_dir = os.path.join("data", "raw", tenant_id)
        if os.path.isdir(tenant_dir):
            for fname in os.listdir(tenant_dir):
                if fname.startswith(file_hash):
                    return os.path.join(tenant_dir, fname)

    # Fallback to flat directory
    raw_dir = "data/raw"
    if not os.path.isdir(raw_dir):
        return None
    for fname in os.listdir(raw_dir):
        if fname.startswith(file_hash):
            return os.path.join(raw_dir, fname)
    return None


def _pick_best_csv(csv_docs: list, query: str) -> tuple:
    """
    Given a list of BronzeDocument objects for CSVs, pick the one whose column
    names best overlap with words in the query.  Falls back to the most recently
    uploaded doc.

    Returns (BronzeDocument, raw_path, df) or (None, None, None).
    """
    query_words = set(re.sub(r"[^a-z0-9 ]", " ", query.lower()).split())
    best_doc  = None
    best_path = None
    best_df   = None
    best_score = -1

    for doc in csv_docs:
        raw_path = _resolve_raw_path(doc.file_hash)
        if not raw_path:
            continue
        try:
            df = pd.read_csv(raw_path)
            df.columns = [c.strip() for c in df.columns]
            col_words = set(
                w for col in df.columns
                for w in re.sub(r"[^a-z0-9 ]", " ", col.lower()).split()
            )
            score = len(query_words & col_words)
            if score > best_score:
                best_score = score
                best_doc   = doc
                best_path  = raw_path
                best_df    = df
        except Exception:
            continue

    # Fallback: use most recent doc even if headers didn't match
    if best_doc is None and csv_docs:
        for doc in csv_docs:
            raw_path = _resolve_raw_path(doc.file_hash)
            if not raw_path:
                continue
            try:
                df = pd.read_csv(raw_path)
                df.columns = [c.strip() for c in df.columns]
                best_doc  = doc
                best_path = raw_path
                best_df   = df
                break
            except Exception:
                continue

    return best_doc, best_path, best_df


# ── Pandas code generator ──────────────────────────────────────────────────────
def _generate_pandas_code(query: str, columns: list, head_sample: list, groq_manager) -> str | None:
    """
    Ask Groq to produce a single-line pandas expression.
    Returns the cleaned code string, or None if generation fails.
    """
    system_prompt = (
        "You are a precise Python/Pandas code generator. "
        "You are given a pandas DataFrame named 'df'. "
        "Generate a SINGLE-LINE Python expression that, when evaluated with eval(), "
        "answers the user's question. The result must be: a scalar, a list, a string, "
        "a pandas Series, or a pandas DataFrame.\n\n"
        f"DataFrame columns: {columns}\n"
        f"Sample rows (first 3): {head_sample}\n\n"
        "STRICT RULES:\n"
        "1. Output ONLY the raw Python expression. NO markdown, NO 'python' prefix, NO explanation.\n"
        "2. Use .str.strip() and .str.lower() when comparing string columns to handle whitespace.\n"
        "3. For counts: use .shape[0] or len(). For lists: use .tolist().\n"
        "4. For multiple metrics: combine with an f-string.\n"
        "5. NEVER use import, os, sys, open, exec, eval, __, subprocess.\n"
        "6. If the question cannot be answered from this DataFrame, output exactly: None\n"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"Question: {query}"},
    ]
    try:
        raw = groq_manager.call_with_fallback(messages, "llama-3.1-8b-instant", temperature=0.0)
    except Exception:
        return None

    # Clean markdown wrappers
    code = raw.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code, flags=re.IGNORECASE)
    code = re.sub(r"```$", "", code).strip()
    code = code.replace("`", "").strip()

    if code.lower().startswith("python"):
        code = code[6:].strip()
    if code == "None":
        return None

    return code


# ── Result formatter ───────────────────────────────────────────────────────────
def _format_result(result, query: str) -> str:
    """Convert a pandas eval result to a clean human-readable string."""
    if isinstance(result, pd.DataFrame):
        if result.empty:
            return "No matching records found."
        return result.to_string(index=False)
    if isinstance(result, pd.Series):
        items = result.dropna().tolist()
        if not items:
            return "No matching records found."
        return ", ".join(str(x) for x in items)
    if isinstance(result, list):
        if not result:
            return "No matching records found."
        return ", ".join(str(x) for x in result)
    if isinstance(result, (int, float)):
        return str(result)
    return str(result)


# ── Main handler ───────────────────────────────────────────────────────────────
def handle_structured_query(
    query: str,
    tenant_id: str,
    q_type: str | None = None,
) -> dict | None:
    """
    Handle structured queries against CSV documents.

    This function covers ALL query types (aggregation, comparison,
    table_lookup, descriptive) — unlike the old csv_handler.py
    which only handled 'aggregation'.

    Returns
    -------
    dict with keys:
        type, raw_result, formatted_evidence, query_executed,
        confidence, document_id, filename
    or None if:
        - no CSV documents exist for this tenant
        - code generation fails
        - execution raises an error
        - safety filter blocks the generated code
    """
    # Step 1: Classify query (allow caller to pass q_type directly)
    if q_type is None:
        q_type = classify_query(query)["type"]

    # Step 2: Fetch tenant's CSV documents
    try:
        from storage.postgres_bronze import SessionLocal, BronzeDocument
        db = SessionLocal()
        csv_docs = (
            db.query(BronzeDocument)
            .filter(
                BronzeDocument.tenant_id == tenant_id,
                BronzeDocument.status == "curated",
                BronzeDocument.source_type == "csv",
            )
            .order_by(BronzeDocument.created_at.desc())
            .all()
        )
        db.close()
    except Exception:
        return None

    if not csv_docs:
        return None

    # Step 3: Pick best matching CSV
    best_doc, raw_path, df = _pick_best_csv(csv_docs, query)
    if best_doc is None or df is None:
        return None

    # Step 4: Generate Pandas expression via Groq
    groq_manager = get_groq_manager()
    columns      = list(df.columns)
    head_sample  = df.head(3).to_dict(orient="records")

    code = _generate_pandas_code(query, columns, head_sample, groq_manager)
    if code is None:
        return None

    # Step 5: Safety check
    if not _is_safe_code(code):
        print(f"[STRUCTURED HANDLER] Safety filter blocked code: {code}")
        return None

    # Step 6: Execute Pandas expression
    print(f"[STRUCTURED HANDLER] Executing: {code}")
    try:
        local_ns = {"df": df, "pd": pd}
        raw_result = eval(code, {}, local_ns)
    except Exception as e:
        print(f"[STRUCTURED HANDLER] Execution error: {e}")
        return None

    # Step 7: Format result
    formatted = _format_result(raw_result, query)

    # Resolve filename for citation
    filename = best_doc.filename or f"Document_{best_doc.document_id[:8]}"

    return {
        "type":               "structured",
        "raw_result":         str(raw_result),
        "formatted_evidence": f"Query: '{query}'\nResult: {formatted}",
        "query_executed":     code,
        "confidence":         "high",
        "document_id":        best_doc.document_id,
        "filename":           filename,
    }



