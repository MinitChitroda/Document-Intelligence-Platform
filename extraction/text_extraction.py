import fitz  # PyMuPDF

def classify_pdf(file_path: str, char_threshold_per_page: int = 50) -> str:
    """
    Given a PDF path, attempt text extraction with PyMuPDF.
    If the average extracted characters per page is below a threshold,
    classify as 'scanned', else 'text_native'.
    """
    try:
        doc = fitz.open(file_path)
        if doc.page_count == 0:
            return "unknown"
            
        total_chars = 0
        for page in doc:
            text = page.get_text()
            total_chars += len(text.strip())
            
        avg_chars = total_chars / doc.page_count
        
        if avg_chars < char_threshold_per_page:
            return "scanned"
        else:
            return "text_native"
    except Exception as e:
        return f"error: {str(e)}"

import re

def clean_text(text: str) -> str:
    """Strip common headers/footers and normalize whitespace."""
    # Remove lines that look like "Page 1 of 10" or just numbers at the top/bottom
    text = re.sub(r'(?im)^\s*(Page\s*\d+|\d+)\s*$', '', text)
    # Normalize whitespace (newlines to spaces, squash multiple spaces)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

from typing import Union

def chunk_text(text: Union[str, dict[int, str]], chunk_size: int = 400, overlap: int = 50) -> Union[list[str], list[dict]]:
    """
    If text is str:
        Chunk text into pieces of approximately `chunk_size` words with `overlap` words.
        Returns list[str].
    If text is dict:
        Chunk within each page separately.
        Returns list[dict] with metadata:
        {"page_number": page_num, "chunk_text": chunk_str, "chunk_type": "text"|"table", "chunk_index": i, "content": chunk_str}
    """
    if isinstance(text, str):
        words = text.split()
        chunks = []
        if not words:
            return chunks
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + chunk_size >= len(words):
                break
        return chunks

    # If dict of {page_num: text}
    chunks = []
    chunk_idx = 0
    for page_num, page_text in text.items():
        words = page_text.split()
        if not words:
            continue
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_str = " ".join(chunk_words)
            chunk_type = "table" if "|" in chunk_str or "\t" in chunk_str or "  " in chunk_str else "text"
            chunks.append({
                "chunk_index": chunk_idx,
                "content": chunk_str,
                "page_number": page_num,
                "chunk_text": chunk_str,
                "chunk_type": chunk_type
            })
            chunk_idx += 1
            if i + chunk_size >= len(words):
                break
    return chunks

def extract_text_native(file_path: str) -> list[dict]:
    """
    Extracts text per page from a native PDF, cleans it, and chunks it.
    Returns a list of chunk dictionaries.
    """
    doc = fitz.open(file_path)
    pages_dict = {}
    
    for idx, page in enumerate(doc):
        page_num = idx + 1
        page_text = page.get_text()
        cleaned = clean_text(page_text)
        if cleaned:
            pages_dict[page_num] = cleaned
            
    # Chunk the page dictionary
    text_chunks = chunk_text(pages_dict, chunk_size=400, overlap=50)
    return text_chunks


# ── Intelligent chunking (Phase 4 addition) ────────────────────────────────────

def _detect_page_content_type(page_text: str) -> str:
    """
    Heuristically detect content type of a page's text.
    Returns 'table', 'list', or 'prose'.
    """
    lines = [l for l in page_text.splitlines() if l.strip()]
    if not lines:
        return "prose"

    # Table: ≥ 3 lines containing '|' OR high average multi-space count
    pipe_lines = sum(1 for l in lines if "|" in l)
    if pipe_lines >= 3:
        return "table"
    avg_gap_count = sum(len(re.findall(r"  +", l)) for l in lines) / len(lines)
    if avg_gap_count >= 2.5 and len(lines) >= 3:
        return "table"

    # List: ≥ 3 lines starting with bullet or numbered marker
    list_pat = re.compile(r"^\s*(?:[-*•]|\d+[.):])\s+")
    list_lines = sum(1 for l in lines if list_pat.match(l))
    if list_lines >= 3:
        return "list"

    return "prose"


def _split_prose_into_paragraphs(text: str, max_words: int = 350, overlap_paras: int = 1) -> list[str]:
    """
    Split prose text at blank-line paragraph boundaries.
    If a paragraph exceeds max_words, further split at sentence boundaries.
    Includes 1-paragraph overlap to preserve context across chunk edges.
    """
    # Split on one or more blank lines
    raw_paragraphs = re.split(r"\n\s*\n", text.strip())
    paragraphs = [p.strip().replace("\n", " ") for p in raw_paragraphs if p.strip()]

    # Sub-split any paragraph that exceeds max_words
    refined: list[str] = []
    for para in paragraphs:
        words = para.split()
        if len(words) <= max_words:
            refined.append(para)
        else:
            # Split at sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current: list[str] = []
            current_words = 0
            for sent in sentences:
                sw = len(sent.split())
                if current_words + sw > max_words and current:
                    refined.append(" ".join(current))
                    current = []
                    current_words = 0
                current.append(sent)
                current_words += sw
            if current:
                refined.append(" ".join(current))

    # Build chunks with overlap
    if not refined:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(refined):
        chunk_paras = refined[i:i + 3]  # up to 3 paragraphs per chunk
        chunks.append("\n\n".join(chunk_paras))
        if i + 3 >= len(refined):
            break
        i += max(1, 3 - overlap_paras)  # overlap by 1 paragraph

    return chunks


def _detect_section_title(page_text: str) -> str:
    """Return the first non-empty line of the page as a candidate section title."""
    for line in page_text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) > 2:
            return stripped[:80]
    return ""


def chunk_text_intelligently(
    text_by_page: dict[int, str],
) -> list[dict]:
    """
    Intelligent chunking that respects content-type boundaries.

    For each page:
      - Tables  → entire page kept as one chunk (no splitting to preserve structure)
      - Lists   → entire page kept as one chunk
      - Prose   → split at paragraph/sentence boundaries with 1-paragraph overlap

    Returns list of dicts:
      {
        "page_number":    int,
        "chunk_text":     str,
        "chunk_type":     "table" | "list" | "prose",
        "section_title":  str,
        "is_multi_page":  bool,
        "chunk_index":    int,
      }
    """
    chunks: list[dict] = []
    chunk_idx = 0

    for page_num, page_text in text_by_page.items():
        if not page_text or not page_text.strip():
            continue

        content_type  = _detect_page_content_type(page_text)
        section_title = _detect_section_title(page_text)

        if content_type in ("table", "list"):
            # Keep entire page as a single chunk to preserve structure
            chunks.append({
                "chunk_index":   chunk_idx,
                "page_number":   page_num,
                "chunk_text":    page_text.strip(),
                "content":       page_text.strip(),
                "chunk_type":    content_type,
                "section_title": section_title,
                "is_multi_page": False,
            })
            chunk_idx += 1
        else:
            # Prose: split at paragraph boundaries
            prose_chunks = _split_prose_into_paragraphs(page_text)
            for pc in prose_chunks:
                if not pc.strip():
                    continue
                chunks.append({
                    "chunk_index":   chunk_idx,
                    "page_number":   page_num,
                    "chunk_text":    pc.strip(),
                    "content":       pc.strip(),
                    "chunk_type":    "prose",
                    "section_title": section_title,
                    "is_multi_page": False,
                })
                chunk_idx += 1

    return chunks

