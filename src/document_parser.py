"""
document_parser.py
------------------
Parses uploaded documents (PDF, DOCX, TXT) into text and provides
field validation for ante-mortem profiles and post-mortem cases.
"""
from __future__ import annotations

import io
from importlib import import_module
from typing import Dict, Any, List


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract raw text from PDF, DOCX, or TXT uploads."""
    ext = filename.lower().split(".")[-1]
    
    if ext == "txt":
        return file_bytes.decode("utf-8", errors="ignore")
        
    elif ext == "pdf":
        try:
            PyPDF2 = import_module("PyPDF2")
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text.append(t)
            return "\n".join(text)
        except Exception as e:
            return f"Error reading PDF: {e}"

    elif ext in ("docx", "doc"):
        try:
            docx = import_module("docx")
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs if p.text])
        except Exception as e:
            return f"Error reading Word document: {e}"

    return ""


def validate_extracted_fields(extracted_data: Dict[str, Any], record_type: str = "ante_mortem") -> List[str]:
    """Identify missing fields required or recommended for reliable DVI matching."""
    missing = []
    
    if record_type == "ante_mortem":
        required = [
            ("reporter_name", "Reporter Name"),
            ("reporter_relationship", "Reporter Relationship"),
            ("missing_person_name", "Missing Person Name"),
            ("sex", "Sex"),
        ]
        recommended = [
            ("age_min", "Age Estimate"),
            ("height_cm_min", "Height Estimate"),
            ("clothing", "Clothing Description"),
            ("dental_notes", "Dental Notes"),
            ("marks", "Scars / Birthmarks / Tattoos"),
        ]
    else:  # post_mortem
        required = [
            ("case_number", "Case Number"),
            ("location_found", "Location Found"),
            ("sex", "Sex"),
        ]
        recommended = [
            ("age_min", "Estimated Age"),
            ("height_cm_min", "Estimated Height"),
            ("clothing", "Clothing Found"),
            ("dental_findings", "Dental Findings"),
            ("marks", "Forensic Marks / Distinguishing Features"),
        ]

    for key, label in required:
        val = extracted_data.get(key)
        if not val or val == "unknown":
            missing.append(f"⚠️ **CRITICAL MISSING**: {label}")

    for key, label in recommended:
        val = extracted_data.get(key)
        if not val or val == [] or val == "unknown":
            missing.append(f"ℹ️ *Recommended Missing*: {label}")

    return missing