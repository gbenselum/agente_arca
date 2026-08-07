"""
Invoice Parser & Extractor Module.
Processes PDF/image invoices dropped in invoices/ directory, extracts structured tax data,
provides OCR fallback, validates legal requirements, and writes a corresponding .json extract file with the same filename.
"""

import os
import json
import re
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from ..models.invoice import InvoiceData, InvoiceParseResult, ReceiptType, SiRADIGCategory
from ..utils.logger import logger

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# Optional OCR integration
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    OCR_AVAILABLE = False


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts raw text from a PDF file using pypdf with fallback warning."""
    if not PdfReader:
        logger.error("pypdf is not installed. Cannot parse PDF.")
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for idx, page in enumerate(reader.pages):
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        if not text.strip():
            logger.warning(f"pypdf extracted 0 text from {pdf_path}. Document might be scanned.")
        return text
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        return ""


def extract_text_via_ocr_fallback(pdf_path: str) -> str:
    """
    Attempts OCR extraction when text is not extractable via standard PDF text stream.
    Gracefully logs if OCR dependencies (Tesseract) are not available.
    """
    if not OCR_AVAILABLE:
        logger.info(f"OCR fallback requested for {pdf_path}, but pytesseract / Pillow is not installed.")
        return ""
    try:
        # If an image file or PDF converted to image
        logger.info(f"Attempting OCR on {pdf_path}...")
        text = pytesseract.image_to_string(pdf_path, lang="spa+eng")
        return text
    except Exception as e:
        logger.warning(f"OCR fallback failed on {pdf_path}: {e}")
        return ""


def detect_suggested_category(text: str) -> SiRADIGCategory:
    """Detects likely SiRADIG deduction category from receipt keywords."""
    clean = text.lower()
    if any(k in clean for k in ["colegio", "escuela", "instituto", "educacion", "educación", "arancel", "matricula", "matrícula", "universidad", "cuota escolar", "uniforme"]):
        return SiRADIGCategory.GASTOS_EDUCACION
    elif any(k in clean for k in ["prepaga", "swiss medical", "osde", "galeno", "medife", "omint", "plan de salud", "cuota asistencial", "asistencia medica"]):
        return SiRADIGCategory.CUOTA_MEDICO_ASSIST
    elif any(k in clean for k in ["medico", "médico", "honorarios", "odontologo", "odontólogo", "psicologo", "psicólogo", "consulta", "clinica", "clínica", "laboratorio", "radiografia", "kinesiologia"]):
        return SiRADIGCategory.MEDICO_PARAMEDICO
    elif any(k in clean for k in ["alquiler", "locacion", "locación", "inmobiliaria", "arrendamiento"]):
        return SiRADIGCategory.ALQUILER_HABITACION
    elif any(k in clean for k in ["servicio domestico", "servicio doméstico", "casas particulares", "personal de casas particulares", "vep", "afip f. 102"]):
        return SiRADIGCategory.CASAS_PARTICULARES
    elif any(k in clean for k in ["seguro de vida", "seguro de retiro", "poliza de vida", "póliza"]):
        return SiRADIGCategory.SEGUROS_VIDA_RETIRO
    elif any(k in clean for k in ["sepelio", "servicios funebres", "inhumacion"]):
        return SiRADIGCategory.GASTOS_SEPELIO
    elif any(k in clean for k in ["donacion", "donación", "fundacion", "fundación", "asociacion civil"]):
        return SiRADIGCategory.DONACIONES
    elif any(k in clean for k in ["interes hipotecario", "intereses hipotecarios", "credito hipotecario", "préstamo hipotecario"]):
        return SiRADIGCategory.INTERES_HIPOTECARIO

    return SiRADIGCategory.GASTOS_EDUCACION


def parse_invoice_text(raw_text: str, filename: Optional[str] = None) -> InvoiceData:
    """
    Parses raw text extracted from invoice into structured InvoiceData model.
    Applies comprehensive regex heuristics for AFIP electronic invoices.
    """
    extracted = {
        "vendor_cuit": "",
        "vendor_name": "",
        "receipt_type": ReceiptType.FACTURA_B,
        "point_of_sale": None,
        "receipt_number": None,
        "issue_date": "",
        "total_amount": 0.0,
        "reimbursed_amount": 0.0,
        "cae": "",
        "cae_due_date": "",
        "concept_description": "",
        "beneficiary_cuil": "",
        "suggested_category": SiRADIGCategory.GASTOS_EDUCACION
    }

    # Default receipt type
    receipt_type = ReceiptType.FACTURA_B

    # Try to extract receipt type from AFIP-style filename
    if filename:
        file_match = re.match(r'^fa_(\d{11})(\d{2})', filename, re.IGNORECASE)
        if file_match:
            type_code = file_match.group(2)
            code_map = {
                "01": ReceiptType.FACTURA_A,
                "06": ReceiptType.FACTURA_B,
                "11": ReceiptType.FACTURA_C,
                "51": ReceiptType.FACTURA_M,
                "02": ReceiptType.NOTA_DE_DEBITO_A,
                "03": ReceiptType.NOTA_DE_CREDITO_A,
                "07": ReceiptType.NOTA_DE_DEBITO_B,
                "08": ReceiptType.NOTA_DE_CREDITO_B,
                "12": ReceiptType.NOTA_DE_DEBITO_C,
                "13": ReceiptType.NOTA_DE_CREDITO_C,
            }
            if type_code in code_map:
                receipt_type = code_map[type_code]

    # Clean text for pattern scanning
    text_clean = raw_text.replace("\n", " ")

    # Check for specific AFIP receipt headers
    if re.search(r'\bFACTURA\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.FACTURA_A
    elif re.search(r'\bFACTURA\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.FACTURA_B
    elif re.search(r'\bFACTURA\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.FACTURA_C
    elif re.search(r'\bFACTURA\s+M\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.FACTURA_M
    elif re.search(r'\bRECIBO\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.RECIBO_B
    elif re.search(r'\bRECIBO\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.RECIBO_C
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_DEBITO_A
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_DEBITO_B
    elif re.search(r'\bNOTA\s+DE\s+DEBITO\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_DEBITO_C
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+A\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_CREDITO_A
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+B\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_CREDITO_B
    elif re.search(r'\bNOTA\s+DE\s+CREDITO\s+C\b', text_clean, re.IGNORECASE):
        receipt_type = ReceiptType.NOTA_DE_CREDITO_C

    extracted["receipt_type"] = receipt_type

    # 1. Vendor CUIT regex pattern
    cuit_match = re.search(r'(?:CUIT|C\.U\.I\.T\.)\s*:?\s*(\d{2}-?\d{8}-?\d{1})', raw_text, re.IGNORECASE)
    if cuit_match:
        extracted["vendor_cuit"] = cuit_match.group(1).replace("-", "")
    elif filename:
        file_match = re.match(r'^fa_(\d{11})', filename, re.IGNORECASE)
        if file_match:
            extracted["vendor_cuit"] = file_match.group(1)

    # Vendor Name / Razon Social
    name_match = re.search(r'(?:Razón Social|Razon Social|Razón Social / Denominación|Apellido y Nombre|Emisor)\s*:?\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    if name_match:
        extracted["vendor_name"] = name_match.group(1).strip()

    # 2. Receipt Number & POS (0000X-000XXXXX or Punto de Venta: X Comp. Nro: Y)
    pos_comp_match = re.search(r'Punto de Venta\s*:?\s*(\d{1,5})\s+Comp\.?\s*Nro\s*:?\s*(\d{1,8})', raw_text, re.IGNORECASE)
    if pos_comp_match:
        extracted["point_of_sale"] = int(pos_comp_match.group(1))
        extracted["receipt_number"] = int(pos_comp_match.group(2))
    else:
        nro_match = re.search(r'(\d{4,5})\s*-\s*(\d{8})', raw_text)
        if nro_match:
            extracted["point_of_sale"] = int(nro_match.group(1))
            extracted["receipt_number"] = int(nro_match.group(2))

    # 3. Issue Date (DD/MM/YYYY or YYYY-MM-DD or Fecha de Emisión: DD/MM/YYYY)
    date_match = re.search(r'(?:Fecha(?:\s+de\s+Emisi[oó]n)?\s*:?\s*)(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text, re.IGNORECASE)
    if date_match:
        extracted["issue_date"] = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"
    else:
        fallback_date = re.search(r'(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text)
        if fallback_date:
            extracted["issue_date"] = f"{fallback_date.group(3)}-{fallback_date.group(2)}-{fallback_date.group(1)}"

    # 4. Total Amount
    def parse_amount(val_str: str) -> float:
        val_str = val_str.strip()
        if "," in val_str and "." in val_str:
            if val_str.rfind(",") > val_str.rfind("."):
                val_str = val_str.replace(".", "").replace(",", ".")
            else:
                val_str = val_str.replace(",", "")
        elif "," in val_str:
            val_str = val_str.replace(",", ".")
        elif "." in val_str and val_str.count(".") > 1:
            val_str = val_str.replace(".", "")
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    amount_match = re.search(r'(?:Importe\s+Total|TOTAL(?:\s+A\s+PAGAR)?|NETO|TOTAL\s*FACTURA\s*:)\s*:?\s*\$?\s*([\d.,]+)', raw_text, re.IGNORECASE)
    if amount_match:
        extracted["total_amount"] = parse_amount(amount_match.group(1))

    # 5. CAE Match (14 digits)
    cae_match = re.search(r'(?:CAE|C\.A\.E\.|CAEA|C\.A\.E\.A\.)\s*(?:N[°ºo\.]?)?\s*:?\s*(\d{14})', raw_text, re.IGNORECASE)
    if cae_match:
        extracted["cae"] = cae_match.group(1)

    # 6. CAE Due Date Match
    cae_due_date_match = re.search(r'(?:Fecha\s+de\s+Vto\.?(?:\s+de)?|VENCIMIENTO(?:\s+DEL)?|VTO\.?(?:\s+DEL)?)\s+CAE\s*:?\s*(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text, re.IGNORECASE)
    if not cae_due_date_match:
        cae_due_date_match = re.search(r'(?:VTO|VENCIMIENTO)\s*:?\s*(\d{2})[/.-](\d{2})[/.-](\d{4})', raw_text, re.IGNORECASE)
    if cae_due_date_match:
        extracted["cae_due_date"] = f"{cae_due_date_match.group(3)}-{cae_due_date_match.group(2)}-{cae_due_date_match.group(1)}"

    # 7. Beneficiary / Client CUIT / DNI
    client_cuit_match = re.search(r'(?:CUIT|CUIL|Documento|Doc)\s*(?:del\s+Comprador|Receptor|Cliente)?\s*:?\s*(\d{2}-?\d{8}-?\d{1})', raw_text, re.IGNORECASE)
    if client_cuit_match:
        extracted["beneficiary_cuil"] = client_cuit_match.group(1).replace("-", "")

    # 8. Category and description
    extracted["suggested_category"] = detect_suggested_category(raw_text)

    # Extract concept / description snippet
    concept_match = re.search(r'(?:Concepto|Descripción|Detalle)\s*:?\s*([^\n\r]{5,100})', raw_text, re.IGNORECASE)
    if concept_match:
        extracted["concept_description"] = concept_match.group(1).strip()
    else:
        extracted["concept_description"] = extracted["suggested_category"].value

    return InvoiceData(**extracted)


def process_pdf_invoice(pdf_file_path: str) -> InvoiceParseResult:
    """
    Reads PDF invoice file, extracts structured data with OCR fallback,
    generates a matching .json file with the same filename.
    Returns structured InvoiceParseResult.
    """
    pdf_path = Path(pdf_file_path)
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_file_path}")
        return InvoiceParseResult(
            success=False,
            file_path=pdf_file_path,
            errors=[f"File not found: {pdf_file_path}"]
        )

    raw_text = extract_text_from_pdf(str(pdf_path))
    method = "pypdf"

    # Fallback to OCR if pypdf returned minimal text
    if len(raw_text.strip()) < 30:
        ocr_text = extract_text_via_ocr_fallback(str(pdf_path))
        if ocr_text.strip():
            raw_text = ocr_text
            method = "ocr"

    parsed_data = parse_invoice_text(raw_text, filename=pdf_path.name)
    parsed_data.source_pdf = pdf_path.name
    parsed_data.extraction_method = method

    # Warnings for missing core fields
    warnings = []
    if not parsed_data.vendor_cuit:
        warnings.append("Vendor CUIT could not be extracted.")
    if parsed_data.point_of_sale is None or parsed_data.receipt_number is None:
        warnings.append("Point of Sale or Receipt Number could not be extracted.")
    if parsed_data.total_amount <= 0:
        warnings.append("Total amount was not extracted or is 0.")
    if not parsed_data.issue_date:
        warnings.append("Issue date could not be extracted.")

    # Write output JSON with identical base name
    json_path = pdf_path.with_suffix(".json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"Generated extraction JSON: {json_path}")
    except Exception as e:
        logger.error(f"Failed to write extraction JSON {json_path}: {e}")

    return InvoiceParseResult(
        success=len(warnings) == 0 or parsed_data.total_amount > 0,
        invoice=parsed_data,
        raw_text=raw_text,
        warnings=warnings,
        file_path=str(pdf_path)
    )
