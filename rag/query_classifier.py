def classify_query(query: str) -> dict:
    """
    Classifies a query into one of: 'aggregation', 'comparison', 'table_lookup', 'descriptive', or 'synthesis'.
    Returns a dictionary with 'type', 'confidence', and 'preferred_purpose'.
    """
    q = query.lower()
    
    # Keyword list checks
    agg_keywords = ["how many", "count", "total", "sum of", "average", "unique", "what are the", "columns", "majority"]
    comp_keywords = ["compare", "difference", "versus", "vs", "similar", "comparison"]
    table_keywords = ["table", "credits", "hours", "schema", "syllabus"]
    synthesis_keywords = ["summarize all", "across all", "compare", "relate", "connect", "which uploaded document", "classify", "purpose", "all uploaded documents"]
    
    # Preferred purpose detection based on Prompt C
    preferred_purpose = None
    if any(w in q for w in ["student", "academic", "course", "grade", "marks"]):
        preferred_purpose = "Academic"
    elif any(w in q for w in ["exam", "nqt", "tcs", "recruitment", "interview"]):
        preferred_purpose = "Recruitment"
    elif any(w in q for w in ["payment", "receipt", "invoice", "paid", "transaction"]):
        preferred_purpose = "Financial"
    
    # Synthesis check
    for word in synthesis_keywords:
        if word in q:
            return {"type": "synthesis", "confidence": 0.95, "preferred_purpose": preferred_purpose}
            
    # Aggregation check
    for word in agg_keywords:
        if word in q:
            return {"type": "aggregation", "confidence": 0.95, "preferred_purpose": preferred_purpose}
            
    # Comparison check
    for word in comp_keywords:
        if word in q:
            return {"type": "comparison", "confidence": 0.90, "preferred_purpose": preferred_purpose}
            
    # Table lookup check
    for word in table_keywords:
        if word in q:
            return {"type": "table_lookup", "confidence": 0.85, "preferred_purpose": preferred_purpose}
            
    # Default is descriptive
    return {"type": "descriptive", "confidence": 1.0, "preferred_purpose": preferred_purpose}
