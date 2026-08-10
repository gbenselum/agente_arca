"""
F.572 PDF Parser, Safe Env Sync & Duplicate Verification Module.
Extracts existing loaded items and registered dependents from an official ARCA F.572 "Vista Previa" PDF export
located in the 'vistaprevia/' directory, safely syncs .env variables, and converts it to JSON.
"""

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from ..models.f572 import DependentModel, F572Data, F572LoadedInvoice
from ..models.invoice import InvoiceData
from ..utils.env_manager import safe_update_env
from ..utils.logger import logger

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[assignment,misc]


def extract_text_from_f572_pdf(pdf_path: str) -> str:
    """Extracts text from F.572 PDF in vistaprevia/ directory."""
    if PdfReader is None:
        logger.error("pypdf is not installed. Cannot read F.572 PDF.")
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
        logger.error(f"Error reading F.572 PDF {pdf_path}: {e}")
        return ""


def parse_f572_pdf_text(raw_text: str) -> F572Data:
    """
    Parses raw text of an F.572 PDF document into structured F572Data model.
    """
    taxpayer_cuit = ""
    taxpayer_name = ""
    fiscal_year: int | None = None
    presentation_date = ""
    dependents: list[DependentModel] = []
    loaded_invoices: list[F572LoadedInvoice] = []

    # Extract CUIT del declarante
    cuit_match = re.search(r"(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})", raw_text, re.IGNORECASE)
    if cuit_match:
        taxpayer_cuit = cuit_match.group(1).replace("-", "")

    # Extract Apellido y Nombre (Taxpayer Name)
    name_match = re.search(r"Apellido y Nombre\s*:?\s*([^\n\r]+)", raw_text, re.IGNORECASE)
    if name_match:
        taxpayer_name = name_match.group(1).strip()

    # Extract Período Fiscal
    periodo_match = re.search(r"(?:PERIODO|PERÍODO)(?:\s*FISCAL)?\s*:?\s*(\d{4})", raw_text, re.IGNORECASE)
    if periodo_match:
        fiscal_year = int(periodo_match.group(1))

    # Extract Registered Dependents (Cargas de Familia: Hijos / Hijas / Cónyuge)
    seen_dependents = set()

    # Pattern 1: CUIL/CUIT <11 digits><Name> <DD/MM/YYYY> (standard tabular export)
    dependent_pattern_1 = re.compile(
        r"(?:CUIL|CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{11})\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s,.-]+?)\s+(\d{2}/\d{2}/\d{4})",
        re.IGNORECASE,
    )

    # Pattern 2: Fallback pattern
    dependent_pattern_2 = re.compile(
        r"(?:HIJO|HIJA|CONYUGE|CÓNYUGE)\s*[\s\S]*?"
        r"(?:CUIT|C\.U\.I\.T\.|CUIL)\s*:?\s*(\d{2}-?\d{8}-?\d{1})[\s\S]*?"
        r"Nombre(?:s)?\s*:?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)",
        re.IGNORECASE,
    )

    for match in dependent_pattern_1.finditer(raw_text):
        cuit = match.group(1).replace("-", "")
        raw_name = match.group(2).strip()
        raw_name = re.sub(r"^,\s*|\s*,$", "", raw_name).strip()
        b_date_raw = match.group(3)
        b_parts = b_date_raw.split("/")
        birth_date_iso = f"{b_parts[2]}-{b_parts[1]}-{b_parts[0]}" if len(b_parts) == 3 else ""

        if cuit not in seen_dependents:
            seen_dependents.add(cuit)
            if "," in raw_name:
                last_name, first_name = [p.strip() for p in raw_name.split(",", 1)]
            else:
                parts = raw_name.split(None, 1)
                last_name = parts[0]
                first_name = parts[1] if len(parts) > 1 else ""

            dependents.append(
                DependentModel(
                    cuit=cuit,
                    first_name=first_name,
                    last_name=last_name,
                    birth_date=birth_date_iso,
                    relationship="HIJO",
                )
            )

    if not dependents:
        for match in dependent_pattern_2.finditer(raw_text):
            cuit = match.group(1).replace("-", "")
            raw_name = match.group(2).strip()
            raw_name = re.sub(r"^,\s*|\s*,$", "", raw_name).strip()
            if cuit not in seen_dependents:
                seen_dependents.add(cuit)
                parts = raw_name.split(None, 1)
                dependents.append(
                    DependentModel(
                        cuit=cuit,
                        first_name=parts[1] if len(parts) > 1 else "",
                        last_name=parts[0] if len(parts) > 0 else "",
                        relationship="HIJO",
                    )
                )

    # Regex pattern to capture invoices listed in F.572 tables:
    invoice_pattern = re.compile(
        r"(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})[\s\S]*?"
        r"(\d{4,5})\s*-\s*(\d{8})[\s\S]*?"
        r"\$?\s*([\d.,]+)",
        re.IGNORECASE,
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

        loaded_invoices.append(
            F572LoadedInvoice(vendor_cuit=cuit, point_of_sale=pos, receipt_number=number, total_amount=amount)
        )

    # Map Spanish months to numbers
    SPANISH_MONTH_MAP = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    # Extract monthly deductions (e.g. Gastos de Educación / Servicio Doméstico)
    months_regex = r"(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)"
    monthly_deduction_pattern = re.compile(
        r"(\d{11})\s*-\s*(.+?)\s+([\d.,]+)Subtotal:\s*\$\n"
        r"("
        + months_regex
        + r")\s+([\d.,]+)\$(?:\n[^\n]+?Familiar:\s*CUIL\s*(\d{11})\s*-\s*([A-Za-zÁÉÍÓÚáéíóúñÑ\s,.-]+?)\s*-)?",
        re.IGNORECASE,
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
        for existing in loaded_invoices:
            if (
                existing.vendor_cuit == cuit
                and existing.month == month_num
                and abs(existing.total_amount - amount) < 0.01
                and existing.point_of_sale is None
                and existing.receipt_number is None
            ):
                is_duplicate = True
                break

        if not is_duplicate:
            vendor_name = match.group(2).strip()
            invoice_entry = F572LoadedInvoice(
                vendor_cuit=cuit,
                vendor_name=vendor_name,
                point_of_sale=None,
                receipt_number=None,
                total_amount=amount,
                month=month_num,
            )
            if match.group(6):
                invoice_entry.dependent_cuit = match.group(6).replace("-", "")
                invoice_entry.dependent_name = match.group(7).strip()

            loaded_invoices.append(invoice_entry)

    return F572Data(
        taxpayer_cuit=taxpayer_cuit,
        taxpayer_name=taxpayer_name,
        fiscal_year=fiscal_year,
        presentation_date=presentation_date,
        dependents=dependents,
        loaded_invoices=loaded_invoices,
    )


def sync_f572_to_env(f572_data: F572Data | dict[str, Any], env_file_path: str = ".env") -> bool:
    """
    Safely syncs extracted F.572 values (Taxpayer CUIT, Fiscal Year, Dependents)
    into the .env configuration file without destroying existing comments or other variables.
    """
    data = F572Data(**f572_data) if isinstance(f572_data, dict) else f572_data
    updates: dict[str, Any] = {}

    if data.taxpayer_cuit:
        updates["ARCA_CUIL"] = data.taxpayer_cuit
        updates["TAXPAYER_CUIT"] = data.taxpayer_cuit
    if data.taxpayer_name:
        updates["TAXPAYER_NAME"] = data.taxpayer_name
    if data.fiscal_year:
        updates["FISCAL_YEAR"] = data.fiscal_year

    for idx, dep in enumerate(data.dependents, start=1):
        updates[f"DEPENDENT_{idx}_CUIT"] = dep.cuit
        if dep.first_name:
            updates[f"DEPENDENT_{idx}_FIRST_NAME"] = dep.first_name
        if dep.last_name:
            updates[f"DEPENDENT_{idx}_LAST_NAME"] = dep.last_name
        if dep.relationship:
            updates[f"DEPENDENT_{idx}_RELATIONSHIP"] = dep.relationship
        if dep.birth_date:
            updates[f"DEPENDENT_{idx}_BIRTH_DATE"] = dep.birth_date
        updates[f"DEPENDENT_{idx}_PERCENTAGE"] = dep.percentage

    return safe_update_env(updates, env_file_path=env_file_path)


def process_vistaprevia_f572(pdf_file_path: str, sync_env: bool = True) -> F572Data:
    """
    Reads F.572 PDF from vistaprevia/, parses existing loaded invoices & dependents,
    writes a corresponding .json extract file with the same base name,
    and safely syncs extracted values into .env file.
    """
    pdf_path = Path(pdf_file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"F.572 PDF file not found at: {pdf_file_path}")

    raw_text = extract_text_from_f572_pdf(str(pdf_path))
    parsed_data = parse_f572_pdf_text(raw_text)
    parsed_data.source_pdf = pdf_path.name

    json_path = pdf_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data.model_dump(), f, indent=2, ensure_ascii=False)

    if sync_env:
        sync_f572_to_env(parsed_data)

    logger.info(f"Extracted F.572 JSON saved to: {json_path}")
    return parsed_data


def is_invoice_already_in_f572(invoice: InvoiceData | dict[str, Any], f572_data: F572Data | dict[str, Any]) -> bool:
    """
    Validates whether a candidate invoice (vendor_cuit, POS, receipt_number, or month/amount)
    is already present in the extracted F.572 data.
    """
    if isinstance(invoice, InvoiceData):
        cand_cuit = invoice.vendor_cuit
        cand_pos = invoice.point_of_sale
        cand_num = invoice.receipt_number
        cand_amount = invoice.total_amount
        issue_date_str = invoice.issue_date
    else:
        cand_cuit = re.sub(r"\D", "", invoice.get("vendor_cuit", ""))
        cand_pos = invoice.get("point_of_sale")
        cand_num = invoice.get("receipt_number")
        cand_amount = float(invoice.get("total_amount") or 0.0)
        issue_date_str = invoice.get("issue_date", "")

    if isinstance(f572_data, F572Data):
        loaded_list = f572_data.loaded_invoices
    else:
        loaded_list = [F572LoadedInvoice(**x) for x in f572_data.get("loaded_invoices", [])]

    cand_month = None
    if issue_date_str:
        parts = issue_date_str.split("-")
        if len(parts) >= 2:
            with contextlib.suppress(ValueError):
                cand_month = int(parts[1])

    for item in loaded_list:
        item_cuit = item.vendor_cuit
        if cand_cuit != item_cuit:
            continue

        item_pos = item.point_of_sale
        item_num = item.receipt_number

        # 1. Match by POS and Receipt Number if both are present in candidate and item
        if cand_pos is not None and cand_num is not None and item_pos is not None and item_num is not None:
            if cand_pos == item_pos and cand_num == item_num:
                logger.info(f"Duplicate detected: Invoice {cand_cuit}-{cand_pos}-{cand_num} already in F.572")
                return True

        # 2. Match by Month and Amount if POS/Num are missing from loaded item (e.g. monthly aggregates)
        item_month = item.month
        item_amount = item.total_amount

        if (item_pos is None or item_num is None) and cand_month is not None and item_month is not None:
            if cand_month == item_month and abs(cand_amount - item_amount) < 0.01:
                logger.info(f"Duplicate detected by month {cand_month} and amount ${cand_amount} for CUIT {cand_cuit}")
                return True

    return False
