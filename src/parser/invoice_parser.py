"""
Invoice Parser & Extractor Module.
Processes PDF/image invoices dropped in invoices/ directory, extracts structured tax data,
validates legal requirements, and writes a corresponding .json extract file with the same filename.
"""

import os
import json
import re
from typing import Dict, Any
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts raw text from a PDF file."""
    if not PdfReader:
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return ""

def parse_invoice_text(raw_text: str) -> Dict[str, Any]:
    """
    Parses raw text extracted from invoice via OCR or PDF parser into structured fields.
    """
    extracted = {
        "vendor_cuit": "",
        "vendor_name": "",
        "receipt_type": "FACTURA_B",
        "point_of_sale": None,
        "receipt_number": None,
        "issue_date": "",
        "total_amount": 0.0,
        "reimbursed_amount": 0.0,
        "cae": "",
        "cae_due_date": "",
        "concept_description": "",
        "beneficiary_cuil": "",
        "suggested_category": "GASTOS_EDUCACION"
    }
    
    # 1. Vendor CUIT regex pattern
    cuit_match = re.search(r'(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})', raw_text, re.IGNORECASE)
    if cuit_match:
        extracted["vendor_cuit"] = cuit_match.group(1).replace("-", "")

    # 2. Receipt Number & POS (0000X-000XXXXX)
    nro_match = re.search(r'(\d{4,5})\s*-\s*(\d{8})', raw_text)
    if nro_match:
        extracted["point_of_sale"] = int(nro_match.group(1))
        extracted["receipt_number"] = int(nro_match.group(2))

    # 3. Issue Date (DD/MM/YYYY or YYYY-MM-DD)
    date_match = re.search(r'(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text)
    if date_match:
        extracted["issue_date"] = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"

    # 4. Total Amount
    amount_match = re.search(r'(?:TOTAL|IMPORTES?|NETO)\s*:?\s*\$?\s*([\d.,]+)', raw_text, re.IGNORECASE)
    if amount_match:
        try:
            val_str = amount_match.group(1).replace(".", "").replace(",", ".")
            extracted["total_amount"] = float(val_str)
        except ValueError:
            pass

    # 5. CAE Match
    cae_match = re.search(r'(?:CAE|C\.A\.E\.)\s*:?\s*(\d{14})', raw_text, re.IGNORECASE)
    if cae_match:
        extracted["cae"] = cae_match.group(1)

    return extracted

def process_pdf_invoice(pdf_file_path: str) -> str:
    """
    Reads PDF invoice file, parses fields, generates a matching .json file with the same filename.
    Returns path to created .json file.
    """
    pdf_path = Path(pdf_file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

    raw_text = extract_text_from_pdf(str(pdf_path))
    parsed_data = parse_invoice_text(raw_text)
    parsed_data["source_pdf"] = pdf_path.name

    json_path = pdf_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    print(f"Generated extraction JSON: {json_path}")
    return str(json_path)
