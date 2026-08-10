"""
Legal Validator Module for ARCA / AFIP SiRADIG F.572 deductions under RG 4003/17.
Validates CUITs (Modulo 11), Receipt types, Punto de Venta, CAE/CAEA, Issue dates, and Dependent eligibility.
"""

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..models.f572 import DependentModel
from ..models.invoice import InvoiceData, ReceiptType, SiRADIGCategory
from ..models.validation import ValidationErrorDetail, ValidationResult
from ..utils.logger import logger

# Valid AFIP CUIT prefixes
VALID_CUIT_PREFIXES = {"20", "23", "24", "27", "30", "33", "34"}


def validate_cuit(cuit: str) -> bool:
    """
    Validates CUIT/CUIL format and Modulo 11 checksum according to official ARCA/AFIP algorithm.
    Supports individual and legal entity prefixes: 20, 23, 24, 27, 30, 33, 34.
    """
    clean_cuit = re.sub(r"\D", "", cuit or "")
    if len(clean_cuit) != 11:
        return False

    prefix = clean_cuit[:2]
    if prefix not in VALID_CUIT_PREFIXES:
        return False

    multipliers = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(clean_cuit[i]) * multipliers[i] for i in range(10))
    mod = total % 11
    verifier = 11 - mod

    if verifier == 11:
        verifier = 0
    elif verifier == 10:
        verifier = 9

    return verifier == int(clean_cuit[10])


def calculate_age_at_date(birth_date_str: str, target_date: datetime) -> int | None:
    """Calculates age in years at a given reference date."""
    if not birth_date_str:
        return None
    try:
        birth_dt = datetime.strptime(birth_date_str, "%Y-%m-%d")
        age = target_date.year - birth_dt.year - ((target_date.month, target_date.day) < (birth_dt.month, birth_dt.day))
        return age
    except Exception:
        return None


def validate_invoice_detailed(
    invoice_data: InvoiceData | dict[str, Any],
    dependents_list: Sequence[DependentModel | dict[str, Any]],
    fiscal_year: int,
) -> ValidationResult:
    """
    Performs comprehensive legal validation returning a structured ValidationResult.
    """
    # Normalize input to InvoiceData
    inv = InvoiceData(**invoice_data) if isinstance(invoice_data, dict) else invoice_data

    errors: list[str] = []
    warnings: list[str] = []
    details: list[ValidationErrorDetail] = []

    # 1. CUIT Emisor Validation
    vendor_cuit = inv.vendor_cuit
    if not vendor_cuit:
        msg = "Missing Vendor CUIT (Emisor)."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(field="vendor_cuit", message=msg, severity="ERROR", error_code="MISSING_CUIT")
        )
    elif not validate_cuit(vendor_cuit):
        msg = f"Invalid Vendor CUIT (Emisor): '{vendor_cuit}'. Modulo 11 validation failed."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(field="vendor_cuit", message=msg, severity="ERROR", error_code="INVALID_CUIT_MOD11")
        )

    # 2. Receipt Type & POS / Number validation
    receipt_type = inv.receipt_type
    if not receipt_type or receipt_type == ReceiptType.UNKNOWN:
        msg = "Missing or Unknown Receipt Type (e.g. FACTURA_A, FACTURA_B, FACTURA_C)."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(
                field="receipt_type", message=msg, severity="ERROR", error_code="INVALID_RECEIPT_TYPE"
            )
        )

    pos = inv.point_of_sale
    number = inv.receipt_number
    if pos is None or pos <= 0 or pos > 99999:
        msg = f"Invalid Point of Sale (Punto de Venta): {pos}. Must be between 1 and 99999."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(field="point_of_sale", message=msg, severity="ERROR", error_code="INVALID_POS")
        )

    if number is None or number <= 0 or number > 99999999:
        msg = f"Invalid Receipt Number: {number}. Must be between 1 and 99999999."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(
                field="receipt_number", message=msg, severity="ERROR", error_code="INVALID_RECEIPT_NUM"
            )
        )

    # 3. Total Amount validation
    if inv.total_amount <= 0:
        msg = f"Total amount must be greater than 0, got: {inv.total_amount}"
        errors.append(msg)
        details.append(
            ValidationErrorDetail(field="total_amount", message=msg, severity="ERROR", error_code="INVALID_AMOUNT")
        )

    if inv.reimbursed_amount > inv.total_amount:
        msg = f"Reimbursed amount ({inv.reimbursed_amount}) cannot exceed total amount ({inv.total_amount})."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(
                field="reimbursed_amount", message=msg, severity="ERROR", error_code="EXCESS_REIMBURSEMENT"
            )
        )

    # 4. Issue Date & Fiscal Year Alignment
    issue_date_str = inv.issue_date
    issue_dt = None
    if not issue_date_str:
        msg = "Missing invoice issue date."
        errors.append(msg)
        details.append(
            ValidationErrorDetail(field="issue_date", message=msg, severity="ERROR", error_code="MISSING_DATE")
        )
    else:
        try:
            issue_dt = datetime.strptime(issue_date_str, "%Y-%m-%d")
            if issue_dt.year != fiscal_year:
                msg = (
                    f"Invoice date {issue_date_str} year ({issue_dt.year}) does not match fiscal year ({fiscal_year})."
                )
                errors.append(msg)
                details.append(
                    ValidationErrorDetail(field="issue_date", message=msg, severity="ERROR", error_code="YEAR_MISMATCH")
                )
        except ValueError:
            msg = f"Invalid issue date format: '{issue_date_str}'. Expected YYYY-MM-DD."
            errors.append(msg)
            details.append(
                ValidationErrorDetail(
                    field="issue_date", message=msg, severity="ERROR", error_code="INVALID_DATE_FORMAT"
                )
            )

    # 5. CAE / CAEA Presence
    if not inv.cae:
        warn = (
            "Comprobante has no CAE/CAEA recorded. In SiRADIG, electronic receipts "
            "usually require an authorization code."
        )
        warnings.append(warn)
        details.append(ValidationErrorDetail(field="cae", message=warn, severity="WARNING", error_code="MISSING_CAE"))
    elif len(inv.cae) != 14 or not inv.cae.isdigit():
        warn = f"CAE code '{inv.cae}' length or format is unexpected (expected 14 digits)."
        warnings.append(warn)
        details.append(
            ValidationErrorDetail(field="cae", message=warn, severity="WARNING", error_code="UNEXPECTED_CAE_FORMAT")
        )

    # 6. Beneficiary CUIT check (if expense is for dependent)
    beneficiary_cuil = inv.beneficiary_cuil
    if beneficiary_cuil:
        if not validate_cuit(beneficiary_cuil):
            msg = f"Invalid Beneficiary CUIT/CUIL: '{beneficiary_cuil}'. Modulo 11 validation failed."
            errors.append(msg)
            details.append(
                ValidationErrorDetail(
                    field="beneficiary_cuil", message=msg, severity="ERROR", error_code="INVALID_BENEFICIARY_CUIT"
                )
            )
        else:
            clean_ben = re.sub(r"\D", "", beneficiary_cuil)

            # Build list of allowed cuits
            allowed_cuits = set()
            dep_map = {}
            for d in dependents_list:
                if isinstance(d, dict):
                    c = re.sub(r"\D", "", d.get("cuit", ""))
                    b_date = d.get("birth_date", "")
                else:
                    c = d.cuit
                    b_date = d.birth_date
                if c:
                    allowed_cuits.add(c)
                    dep_map[c] = b_date

            if allowed_cuits and clean_ben not in allowed_cuits:
                msg = f"Beneficiary CUIT {beneficiary_cuil} is not registered in taxpayer's family dependents (.env)."
                errors.append(msg)
                details.append(
                    ValidationErrorDetail(
                        field="beneficiary_cuil", message=msg, severity="ERROR", error_code="BENEFICIARY_NOT_REGISTERED"
                    )
                )

            # Check age limit for education (up to 24 years old under RG 4003/17)
            if inv.suggested_category == SiRADIGCategory.GASTOS_EDUCACION and clean_ben in dep_map:
                b_date = dep_map[clean_ben]
                if b_date and issue_dt:
                    age = calculate_age_at_date(b_date, issue_dt)
                    if age is not None and age > 24:
                        msg = (
                            f"Education expense not deductible: Beneficiary age is {age} "
                            f"(maximum eligible age is 24 under RG 4003/17)."
                        )
                        errors.append(msg)
                        details.append(
                            ValidationErrorDetail(
                                field="beneficiary_cuil",
                                message=msg,
                                severity="ERROR",
                                error_code="EDUCATION_AGE_EXCEEDED",
                            )
                        )

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(f"Legal validation failed for invoice {inv.invoice_id}: {errors}")
    else:
        logger.debug(f"Legal validation passed for invoice {inv.invoice_id}")

    return ValidationResult(
        is_valid=is_valid, invoice_id=inv.invoice_id, errors=errors, warnings=warnings, details=details
    )
