import re

def classify_document_purpose(text: str) -> str:
    """
    Classify the purpose of a document based on its text content.
    Returns one of: Academic, Recruitment, Financial, Administrative, Other
    """
    if not text:
        return "Other"

    text_lower = text.lower()

    # Keyword lists for each category
    academic_keywords = [
        "student", "academic", "course", "semester", "cgpa", "sgpa", 
        "branch", "engineering", "marks", "grade", "faculty", "syllabus", 
        "university", "college", "degree", "enrollment"
    ]
    
    recruitment_keywords = [
        "recruitment", "interview", "candidate", "nqt", "examination",
        "hiring", "job", "offer", "salary", "onboarding", "resume",
        "aptitude", "reporting time", "venue", "tcs"
    ]
    
    financial_keywords = [
        "payment", "receipt", "invoice", "transaction", "amount", "rupees", 
        "paid", "upi", "bank", "tax", "fee", "bill", "₹", "rs", "balance",
        "credit", "debit", "remittance"
    ]
    
    administrative_keywords = [
        "policy", "guideline", "administrative", "leave", "holiday",
        "circular", "notice", "memorandum", "compliance", "terms and conditions",
        "agreement"
    ]

    # Count occurrences
    scores = {
        "Academic": sum(len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower)) for kw in academic_keywords),
        "Recruitment": sum(len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower)) for kw in recruitment_keywords),
        "Financial": sum(len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower)) for kw in financial_keywords),
        "Administrative": sum(len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower)) for kw in administrative_keywords),
    }

    # Add exceptions for non-word boundary symbols like ₹
    scores["Financial"] += text_lower.count("₹") * 2
    
    # Boost certain high-signal words
    if "receipt" in text_lower or "invoice" in text_lower or "transaction" in text_lower:
        scores["Financial"] += 5
        
    if "tcs" in text_lower or "nqt" in text_lower:
        scores["Recruitment"] += 5

    # Find the max score
    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    # If the score is too low, default to Other
    if best_score < 2:
        return "Other"

    return best_category
