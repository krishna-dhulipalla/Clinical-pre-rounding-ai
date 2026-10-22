import re
from typing import List, Tuple

class Redactor:
    def __init__(self, patient_name: str = None):
        self.patient_name = patient_name
        self.replacements = []

    def redact(self, text: str) -> str:
        """
        Redacts PHI from text using regex and known entities.
        """
        # Keep citation identifiers stable so evidence still resolves in the UI.
        citations = []
        def protect_citation(match):
            citations.append(match.group(0))
            return f"\x00CITATION{len(citations) - 1}\x00"
        redacted_text = re.sub(r"\[\[[^\]\n]+\]\]", protect_citation, text)

        # 1. Redact Patient Name (if known)
        if self.patient_name:
            # Handle "John Smith" -> [PATIENT_NAME]
            # Case insensitive simple replacement
            pattern = re.compile(re.escape(self.patient_name), re.IGNORECASE)
            redacted_text = pattern.sub("[PATIENT_NAME]", redacted_text)
            
            # First Name / Last Name split?
            # For strict safety, maybe. For now, full name.

        # 2. Redact Dates (YYYY-MM-DD or MM/DD/YYYY)
        # Regex for YYYY-MM-DD
        date_pattern = re.compile(r'\b\d{4}-\d{2}-\d{2}\b') 
        redacted_text = date_pattern.sub("[DATE]", redacted_text)
        redacted_text = re.sub(r'\b\d{2}/\d{2}/\d{4}\b', "[DATE]", redacted_text)

        # 3. Redact MRNs / IDs (Simple heuristics)
        # Assuming UUIDs or numeric IDs are PHI if they aren't part of our internal references?
        # Actually, our Facts have citations [[Observation/123]]. We DON'T want to redact those internal IDs 
        # because the UI needs them.
        # But we SHOULD redact MRNs if they appear in text.
        # For this MVP, we will trust internal IDs like Observation/xyz are safe, 
        # but redact loose numbers that look like SSN/Phone?
        
        # Phone: (123) 456-7890 or 123-456-7890
        phone_pattern = re.compile(r'(?<!\w)(?:\+\d{1,2}\s)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}\b')
        redacted_text = phone_pattern.sub("[PHONE]", redacted_text)
        for index, citation in enumerate(citations):
            redacted_text = redacted_text.replace(f"\x00CITATION{index}\x00", citation)

        return redacted_text
