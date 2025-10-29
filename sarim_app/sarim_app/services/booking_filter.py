import re
import frappe

@frappe.whitelist()
def prefilter_booking_email(subject, body):
    """Lightweight prefilter to detect likely cab booking emails (no score-based system)"""
    text = (subject + " " + body).lower()

    # ✅ Keyword sets
    partial_keywords = ['book', 'cab', 'pickup', 'drop']
    exact_keywords = ['ride', 'trip', 'vehicle', 'driver', 'itinerary', 'reservation', 'confirmed']

    keyword_hits = 0

    for k in partial_keywords:
        if k in text:
            keyword_hits += 1

    for k in exact_keywords:
        if re.search(rf'\b{k}\b', text):
            keyword_hits += 1

    # ✅ Contextual patterns
    strong_patterns = [
        r"cab\s+(booking|confirmed|request)",
        r"(pickup|drop)\s+(location|time|from|to)",
        r"airport\s+(pickup|drop)",
        r"driver\s+(details|assigned|mobile)",
        r"trip\s+(details|confirmation)"
    ]
    pattern_hits = sum(bool(re.search(p, text)) for p in strong_patterns)

    # ✅ Date/time detection
    has_date = bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text))
    has_time = bool(re.search(r'\b\d{1,2}:\d{2}\s*(am|pm)?\b', text))

    # ✅ Final simple decision
    if (keyword_hits >= 2) or (pattern_hits >= 1) or (keyword_hits >= 1 and (has_date or has_time)):
        reason = f"Matched {keyword_hits} keywords, {pattern_hits} patterns"
        return {"is_likely_booking": True, "reason": reason}
    
    return {"is_likely_booking": False, "reason": "No strong booking indicators"}
