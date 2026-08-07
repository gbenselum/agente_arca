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

def parse_invoice_text(raw_text: str, filename: str = None) -> Dict[str, Any]:
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

    # Default receipt type
    receipt_type = "FACTURA_B"

    # Try to extract receipt type from AFIP-style filename
    if filename:
        # e.g., fa_3361196995911000886283665800621202607234_174686_86283665800621.pdf
        file_match = re.match(r'^fa_(\d{11})(\d{2})', filename, re.IGNORECASE)
        if file_match:
            type_code = file_match.group(2)
            code_map = {
                "01": "FACTURA_A",
                "06": "FACTURA_B",
                "11": "FACTURA_C",
                "02": "NOTA_DE_DEBITO_A",
                "03": "NOTA_DE_CREDITO_A",
                "07": "NOTA_DE_DEBITO_B",
                "08": "NOTA_DE_CREDITO_B",
                "12": "NOTA_DE_DEBITO_C",
                "13": "NOTA_DE_CREDITO_C",
            }
            if type_code in code_map:
                receipt_type = code_map[type_code]

    # Try to override/extract from raw text if explicit text matches
    text_clean = raw_text.replace("\n", " ")
    if re.search(r'\bFACTURA\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = "FACTURA_A"
    elif re.search(r'\bFACTURA\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = "FACTURA_B"
    elif re.search(r'\bFACTURA\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = "FACTURA_C"
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_DEBITO_A"
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_DEBITO_B"
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_DEBITO_C"
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_CREDITO_A"
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_CREDITO_B"
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = "NOTA_DE_CREDITO_C"

    extracted["receipt_type"] = receipt_type
    
    # 1. Vendor CUIT regex pattern
    cuit_match = re.search(r'(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})', raw_text, re.IGNORECASE)
    if cuit_match:
        extracted["vendor_cuit"] = cuit_match.group(1).replace("-", "")
    elif filename:
        file_match = re.match(r'^fa_(\d{11})', filename, re.IGNORECASE)
        if file_match:
            extracted["vendor_cuit"] = file_match.group(1)

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
    def parse_amount(val_str: str) -> float:
        val_str = val_str.strip()
        if "," in val_str:
            val_str = val_str.replace(".", "").replace(",", ".")
        elif "." in val_str:
            if val_str.count(".") > 1:
                val_str = val_str.replace(".", "")
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    amount_match = re.search(r'(?:TOTAL(?:\s+A\s+PAGAR)?|IMPORTES?|NETO|FACTURA\s*:)\s*:?\s*\$?\s*([\d.,]+)', raw_text, re.IGNORECASE)
    if amount_match:
        extracted["total_amount"] = parse_amount(amount_match.group(1))

    # 5. CAE Match
    cae_match = re.search(r'(?:CAE|C\.A\.E\.)\s*:?\s*(\d{14})', raw_text, re.IGNORECASE)
    if cae_match:
        extracted["cae"] = cae_match.group(1)

    # 6. CAE Due Date Match
    cae_due_date_match = re.search(r'(?:VENCIMIENTO|VTO\.?)(?:\s+DEL)?\s+CAE\s*:?\s*(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text, re.IGNORECASE)
    if cae_due_date_match:
        extracted["cae_due_date"] = f"{cae_due_date_match.group(3)}-{cae_due_date_match.group(2)}-{cae_due_date_match.group(1)}"

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
    parsed_data = parse_invoice_text(raw_text, filename=pdf_path.name)
    parsed_data["source_pdf"] = pdf_path.name

    json_path = pdf_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    print(f"Generated extraction JSON: {json_path}")
    return str(json_path)
