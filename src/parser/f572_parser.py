"""
F.572 PDF Parser, Env Sync & Duplicate Verification Module.
Extracts existing loaded items and registered dependents from an official ARCA F.572 "Vista Previa" PDF export
located in the 'vistaprevia/' directory, populates .env variables, and converts it to JSON.
"""

import os
import json
import re
from typing import Dict, Any, List
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

def extract_text_from_f572_pdf(pdf_path: str) -> str:
    """Extracts text from F.572 PDF in vistaprevia/ directory."""
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
        print(f"Error reading F.572 PDF {pdf_path}: {e}")
        return ""

def parse_f572_pdf_text(raw_text: str) -> Dict[str, Any]:
    """
    Parses raw text of an F.572 PDF document into structured sections, loaded invoices list, and registered dependents.
    """
    f572_data = {
        "taxpayer_cuit": "",
        "taxpayer_name": "",
        "fiscal_year": None,
        "presentation_date": "",
        "dependents": [],
        "loaded_invoices": []
    }

    # Extract CUIT del declarante
    cuit_match = re.search(r'(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})', raw_text, re.IGNORECASE)
    if cuit_match:
        f572_data["taxpayer_cuit"] = cuit_match.group(1).replace("-", "")

    # Extract Apellido y Nombre (Taxpayer Name)
    name_match = re.search(r'Apellido y Nombre\s*:?\s*([^\n]+)', raw_text, re.IGNORECASE)
    if name_match:
        f572_data["taxpayer_name"] = name_match.group(1).strip()

    # Extract Período Fiscal
    periodo_match = re.search(r'(?:PERIODO|PERÍODO)(?:\s*FISCAL)?\s*:?\s*(\d{4})', raw_text, re.IGNORECASE)
    if periodo_match:
        f572_data["fiscal_year"] = int(periodo_match.group(1))

    # Extract Registered Dependents (Cargas de Familia: Hijos / Hijas / Cónyuge)
    seen_dependents = set()
    
    # Pattern 1: CUIL/CUIT <11 digits><Name> <DD/MM/YYYY> (typically found in newer PDF table exports)
    dependent_pattern_1 = re.compile(
        r'(?:CUIL|CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{11})\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s,.-]+?)\s+(\d{2}/\d{2}/\d{4})',
        re.IGNORECASE
    )
    
    # Pattern 2: Fallback pattern
    dependent_pattern_2 = re.compile(
        r'(?:HIJO|HIJA|CONYUGE|CÓNYUGE)\s*[\s\S]*?'
        r'(?:CUIT|C\.U\.I\.T\.|CUIL)\s*:?\s*(\d{2}-?\d{8}-?\d{1})[\s\S]*?'
        r'Nombre(?:s)?\s*:?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)',
        re.IGNORECASE
    )

    for match in dependent_pattern_1.finditer(raw_text):
        cuit = match.group(1).replace("-", "")
        name = match.group(2).strip()
        name = re.sub(r'^,\s*|\s*,$', '', name).strip()
        if cuit not in seen_dependents:
            seen_dependents.add(cuit)
            f572_data["dependents"].append({
                "cuit": cuit,
                "name": name
            })

    if not f572_data["dependents"]:
        for match in dependent_pattern_2.finditer(raw_text):
            cuit = match.group(1).replace("-", "")
            name = match.group(2).strip()
            name = re.sub(r'^,\s*|\s*,$', '', name).strip()
            if cuit not in seen_dependents:
                seen_dependents.add(cuit)
                f572_data["dependents"].append({
                    "cuit": cuit,
                    "name": name
                })

    # Regex pattern to capture invoices listed in F.572 tables:
    invoice_pattern = re.compile(
        r'(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})[\s\S]*?'
        r'(\d{4,5})\s*-\s*(\d{8})[\s\S]*?'
        r'\$?\s*([\d.,]+)',
        re.IGNORECASE
    )

    for match in invoice_pattern.finditer(raw_text):
        cuit = match.group(1).replace("-", "")
        pos = int(match.group(2))
        number = int(match.group(3))
        amount_str = match.group(4).replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.0

        f572_data["loaded_invoices"].append({
            "vendor_cuit": cuit,
            "point_of_sale": pos,
            "receipt_number": number,
            "total_amount": amount
        })

    # Map Spanish months to numbers
    SPANISH_MONTH_MAP = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }

    # Extract monthly deductions (e.g. Gastos de Educación)
    months_regex = r'(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)'
    monthly_deduction_pattern = re.compile(
        r'(\d{11})\s*-\s*(.+?)\s+([\d.,]+)Subtotal:\s*\$\n'
        r'(' + months_regex + r')\s+([\d.,]+)\$(?:\n[^\n]+?Familiar:\s*CUIL\s*(\d{11})\s*-\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s,.-]+?)\s*-)?',
        re.IGNORECASE
    )

    for match in monthly_deduction_pattern.finditer(raw_text):
        cuit = match.group(1).replace("-", "")
        month_name = match.group(4).lower()
        month_num = SPANISH_MONTH_MAP.get(month_name)
        amount_str = match.group(5).replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.0

        # Avoid duplicate entries in loaded_invoices
        is_duplicate = False
        for existing in f572_data["loaded_invoices"]:
            if (existing.get("vendor_cuit") == cuit and 
                existing.get("month") == month_num and 
                abs(existing.get("total_amount", 0.0) - amount) < 0.01 and
                existing.get("point_of_sale") is None and
                existing.get("receipt_number") is None):
                is_duplicate = True
                break
        
        if not is_duplicate:
            vendor_name = match.group(2).strip()
            invoice_entry = {
                "vendor_cuit": cuit,
                "vendor_name": vendor_name,
                "point_of_sale": None,
                "receipt_number": None,
                "total_amount": amount,
                "month": month_num
            }
            if match.group(6):
                invoice_entry["dependent_cuit"] = match.group(6).replace("-", "")
                invoice_entry["dependent_name"] = match.group(7).strip()

            f572_data["loaded_invoices"].append(invoice_entry)

    return f572_data

def sync_f572_to_env(f572_data: Dict[str, Any], env_file_path: str = ".env") -> bool:
    """
    Loads/syncs extracted F.572 values (Taxpayer CUIT, Fiscal Year, Dependents CUIT/Names)
    into the .env configuration file.
    """
    env_path = Path(env_file_path)
    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    env_map = {}
    for line in existing_lines:
        line_str = line.strip()
        if line_str and not line_str.startswith("#") and "=" in line_str:
            key, val = line_str.split("=", 1)
            env_map[key.strip()] = val.strip()

    # Update extracted taxpayer details
    if f572_data.get("taxpayer_cuit"):
        env_map["ARCA_CUIL"] = f572_data["taxpayer_cuit"]
        env_map["TAXPAYER_CUIT"] = f572_data["taxpayer_cuit"]
    if f572_data.get("taxpayer_name"):
        env_map["TAXPAYER_NAME"] = f572_data["taxpayer_name"]
    if f572_data.get("fiscal_year"):
        env_map["FISCAL_YEAR"] = str(f572_data["fiscal_year"])

    # Update dependents from F.572
    for idx, dep in enumerate(f572_data.get("dependents", []), start=1):
        env_map[f"DEPENDENT_{idx}_CUIT"] = dep.get("cuit", "")
        if dep.get("name"):
            name_str = dep["name"]
            if "," in name_str:
                parts = [p.strip() for p in name_str.split(",", 1)]
                last_name = parts[0]
                first_name = parts[1]
            else:
                parts = name_str.split(None, 1)
                last_name = parts[0]
                first_name = parts[1] if len(parts) > 1 else ""

            env_map[f"DEPENDENT_{idx}_FIRST_NAME"] = first_name
            env_map[f"DEPENDENT_{idx}_LAST_NAME"] = last_name


    # Re-write .env file
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("# Automatically synced from F.572 PDF in vistaprevia/\n")
        for k, v in env_map.items():
            f.write(f"{k}={v}\n")

    print(f"Synced F.572 parameters into environment file: {env_path}")
    return True

def process_vistaprevia_f572(pdf_file_path: str, sync_env: bool = True) -> Dict[str, Any]:
    """
    Reads F.572 PDF from vistaprevia/, parses existing loaded invoices & dependents,
    writes a corresponding .json extract file with the same base name,
    and automatically syncs extracted values into .env file.
    """
    pdf_path = Path(pdf_file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"F.572 PDF file not found at: {pdf_file_path}")

    raw_text = extract_text_from_f572_pdf(str(pdf_path))
    parsed_data = parse_f572_pdf_text(raw_text)
    parsed_data["source_pdf"] = pdf_path.name

    json_path = pdf_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    if sync_env:
        sync_f572_to_env(parsed_data)

    print(f"Extracted F.572 JSON saved to: {json_path}")
    return parsed_data

def is_invoice_already_in_f572(invoice: Dict[str, Any], f572_data: Dict[str, Any]) -> bool:
    """
    Validates whether a candidate invoice (vendor_cuit, POS, receipt_number, or month/amount)
    is already present in the extracted F.572 data.
    """
    cand_cuit = re.sub(r'\D', '', invoice.get("vendor_cuit", ""))
    cand_pos = invoice.get("point_of_sale")
    cand_num = invoice.get("receipt_number")
    cand_amount = float(invoice.get("total_amount") or 0.0)

    # Parse month from candidate invoice (issue_date format is YYYY-MM-DD)
    cand_month = None
    issue_date_str = invoice.get("issue_date", "")
    if issue_date_str:
        parts = issue_date_str.split("-")
        if len(parts) >= 2:
            try:
                cand_month = int(parts[1])
            except ValueError:
                pass

    for item in f572_data.get("loaded_invoices", []):
        item_cuit = re.sub(r'\D', '', item.get("vendor_cuit", ""))
        if cand_cuit != item_cuit:
            continue

        item_pos = item.get("point_of_sale")
        item_num = item.get("receipt_number")

        # 1. Match by POS and Receipt Number if both are present in candidate and item
        if cand_pos is not None and cand_num is not None and item_pos is not None and item_num is not None:
            if cand_pos == item_pos and cand_num == item_num:
                return True

        # 2. Match by Month and Amount if POS/Num are missing from loaded item (e.g. monthly aggregates)
        item_month = item.get("month")
        item_amount = float(item.get("total_amount") or 0.0)

        if (item_pos is None or item_num is None) and cand_month is not None and item_month is not None:
            if cand_month == item_month and abs(cand_amount - item_amount) < 0.01:
                return True

    return False
