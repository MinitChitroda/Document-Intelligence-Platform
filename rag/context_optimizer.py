import re
from typing import List, Dict, Any

def get_words(text: str) -> set:
    """Extract lowercased alphanumeric words for Jaccard similarity."""
    return set(re.findall(r'\b\w+\b', text.lower()))

def optimize_context(chunks: List[Any], overlap_threshold: float = 0.8) -> List[Dict[str, Any]]:
    """
    Optimizes retrieved chunks by:
    1. Removing exact duplicates.
    2. Removing highly overlapping chunks (Jaccard similarity > threshold).
    3. Merging chunks that belong to the exact same document and page.
    """
    if not chunks:
        return []

    # Standardize to dicts
    dict_chunks = []
    for c in chunks:
        if hasattr(c, "to_dict"):
            dict_chunks.append(c.to_dict())
        elif isinstance(c, dict):
            dict_chunks.append(c)
        else:
            # Fallback if unknown object
            dict_chunks.append({"chunk_text": str(c)})

    # Sort chunks by document_id and page_number to facilitate adjacency merging
    # We use empty strings/0 as fallbacks for missing keys
    dict_chunks.sort(key=lambda x: (x.get("document_id", ""), x.get("page_number", 0), -x.get("confidence_score", 0.0)))

    optimized = []
    seen_texts = set()
    seen_words_list = []

    for chunk in dict_chunks:
        text = chunk.get("chunk_text", "").strip()
        if not text:
            continue
            
        # 1. Exact Duplicate Check
        if text in seen_texts:
            continue
            
        # 2. Semantic Overlap Check
        words = get_words(text)
        if not words:
            continue
            
        is_overlap = False
        for seen_words in seen_words_list:
            intersection = len(words.intersection(seen_words))
            union = max(len(words), len(seen_words)) # Simplification to check containment mostly
            if union > 0 and (intersection / union) > overlap_threshold:
                is_overlap = True
                break
                
        if is_overlap:
            continue
            
        # Valid chunk, record it
        seen_texts.add(text)
        seen_words_list.append(words)
        
        # 3. Adjacency Merging
        # Check if we can merge with the previous chunk
        if optimized:
            prev_chunk = optimized[-1]
            if (prev_chunk.get("document_id") == chunk.get("document_id") and 
                prev_chunk.get("document_id") is not None and
                prev_chunk.get("page_number") == chunk.get("page_number")):
                
                # Merge text
                prev_chunk["chunk_text"] += "\n...\n" + text
                # Keep the higher score
                prev_chunk["confidence_score"] = max(prev_chunk.get("confidence_score", 0.0), chunk.get("confidence_score", 0.0))
                continue
                
        # If not merged, append as new
        optimized.append(dict(chunk)) # copy

    return optimized
