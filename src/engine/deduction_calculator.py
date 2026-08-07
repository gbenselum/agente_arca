"""
Deduction Calculator & Annual Caps Engine under ARCA / AFIP RG 4003/17.
Computes net deductible amount, category rates, and enforces annual legal caps (MNI, GNA).
"""

from typing import Dict, Any, List, Optional, Union
from ..models.invoice import InvoiceData, SiRADIGCategory
from ..models.deduction import DeductionResult, FiscalYearCaps, AnnualDeductionSummary
from ..utils.logger import logger

# Base deductible rates per RG 4003/17
CATEGORY_RATES: Dict[str, float] = {
    "MEDICO_PARAMEDICO": 0.40,
    "CUOTA_MEDICO_ASSIST": 1.00,
    "GASTOS_EDUCACION": 1.00,
    "ALQUILER_HABITACION": 0.40,
    "ALQUILER_ADICIONAL_10": 0.10,
    "CASAS_PARTICULARES": 1.00,
    "INTERES_HIPOTECARIO": 1.00,
    "DONACIONES": 1.00,
    "SEGUROS_VIDA_RETIRO": 1.00,
    "GASTOS_SEPELIO": 1.00
}

# Fiscal year default caps (Minimo No Imponible Anual and references)
# Figures in ARS. Can be overridden via config or parameters.
FISCAL_YEAR_DEFAULT_CAPS: Dict[int, FiscalYearCaps] = {
    2024: FiscalYearCaps(
        fiscal_year=2024,
        mni_anual=3091035.00,
        gna_anual=18000000.00,
        notes="Valores RG 5531/24 - Período fiscal 2024"
    ),
    2025: FiscalYearCaps(
        fiscal_year=2025,
        mni_anual=4120000.00,
        gna_anual=24000000.00,
        notes="Valores Proyectados IPC - Período fiscal 2025"
    ),
    2026: FiscalYearCaps(
        fiscal_year=2026,
        mni_anual=5500000.00,
        gna_anual=32000000.00,
        notes="Valores Estimados Base - Período fiscal 2026"
    )
}


def get_fiscal_caps(fiscal_year: int) -> FiscalYearCaps:
    """Returns official or estimated fiscal caps for a given year."""
    return FISCAL_YEAR_DEFAULT_CAPS.get(
        fiscal_year,
        FiscalYearCaps(fiscal_year=fiscal_year, mni_anual=5500000.00, gna_anual=32000000.00)
    )


def compute_deduction(
    invoice_data: Union[InvoiceData, Dict[str, Any]],
    siradig_code: str,
    fiscal_year: int = 2026,
    cumulative_category_total: float = 0.0,
    custom_caps: Optional[FiscalYearCaps] = None
) -> Dict[str, Any]:
    """
    Computes net deductible amount, category rate, and checks annual caps based on RG 4003/17.
    Returns a dictionary result (fully serializable) matching DeductionResult schema.
    """
    if isinstance(invoice_data, InvoiceData):
        total_amount = invoice_data.total_amount
        reimbursed_amount = invoice_data.reimbursed_amount
        inv_id = invoice_data.invoice_id
    else:
        total_amount = float(invoice_data.get("total_amount", 0.0))
        reimbursed_amount = float(invoice_data.get("reimbursed_amount", 0.0))
        pos = invoice_data.get("point_of_sale", 0) or 0
        num = invoice_data.get("receipt_number", 0) or 0
        cuit = invoice_data.get("vendor_cuit", "UNKNOWN")
        inv_id = invoice_data.get("invoice_id", f"{cuit}-{pos:04d}-{num:08d}")

    caps = custom_caps or get_fiscal_caps(fiscal_year)
    mni = caps.mni_anual
    gna = caps.gna_anual or (mni * 6)  # Standard estimated baseline

    net_out_of_pocket = max(0.0, total_amount - reimbursed_amount)
    rate = CATEGORY_RATES.get(siradig_code, 1.00)
    subtotal_before_cap = round(net_out_of_pocket * rate, 2)

    # Determine legal annual cap limit for this category
    annual_cap_limit: Optional[float] = None
    cap_description: Optional[str] = None

    if siradig_code in ("MEDICO_PARAMEDICO", "CUOTA_MEDICO_ASSIST", "DONACIONES"):
        # Capped at 5% of GNA (Ganancia Neta Anual)
        annual_cap_limit = round(0.05 * gna, 2)
        cap_description = f"5% de Ganancia Neta Anual (${annual_cap_limit:,.2f})"

    elif siradig_code == "GASTOS_EDUCACION":
        # Capped at 40% of MNI Anual
        annual_cap_limit = round(0.40 * mni, 2)
        cap_description = f"40% del MNI Anual (${annual_cap_limit:,.2f})"

    elif siradig_code == "CASAS_PARTICULARES":
        # Capped at 100% of MNI Anual
        annual_cap_limit = round(1.00 * mni, 2)
        cap_description = f"100% del MNI Anual (${annual_cap_limit:,.2f})"

    elif siradig_code == "ALQUILER_HABITACION":
        # Capped at lesser between 40% paid and 100% MNI Anual
        annual_cap_limit = round(1.00 * mni, 2)
        cap_description = f"Hasta 100% del MNI Anual (${annual_cap_limit:,.2f})"

    elif siradig_code in ("SEGUROS_VIDA_RETIRO", "INTERES_HIPOTECARIO", "GASTOS_SEPELIO"):
        annual_cap_limit = round(0.40 * mni, 2)
        cap_description = f"Tope legal específico RG 4003 (${annual_cap_limit:,.2f})"

    # Check if cumulative total exceeds the annual cap
    warnings: List[str] = []
    cap_exceeded = False
    computable_deduction = subtotal_before_cap

    if annual_cap_limit is not None:
        remaining_cap = max(0.0, annual_cap_limit - cumulative_category_total)
        if subtotal_before_cap > remaining_cap:
            cap_exceeded = True
            computable_deduction = remaining_cap
            warn_msg = (
                f"Category {siradig_code} reached annual cap limit ({cap_description}). "
                f"Subtotal before cap: ${subtotal_before_cap:,.2f}, remaining eligible: ${remaining_cap:,.2f}."
            )
            warnings.append(warn_msg)
            logger.warning(warn_msg)

    result = {
        "invoice_id": inv_id,
        "siradig_code": siradig_code,
        "gross_amount": total_amount,
        "reimbursed_amount": reimbursed_amount,
        "net_out_of_pocket": net_out_of_pocket,
        "deductible_rate": rate,
        "subtotal_before_cap": subtotal_before_cap,
        "applied_annual_cap": annual_cap_limit,
        "computable_deduction": round(computable_deduction, 2),
        "requires_employer_cap_check": True,
        "warnings": warnings,
        "cap_exceeded": cap_exceeded,
        "cap_limit_description": cap_description
    }
    return result


def compute_batch_deductions(
    invoices: List[Union[InvoiceData, Dict[str, Any]]],
    fiscal_year: int = 2026,
    custom_caps: Optional[FiscalYearCaps] = None
) -> AnnualDeductionSummary:
    """
    Computes cumulative deductions across a batch of invoices, enforcing sequential category caps.
    """
    caps = custom_caps or get_fiscal_caps(fiscal_year)
    cumulative_totals: Dict[str, float] = {}
    category_breakdown: Dict[str, Dict[str, float]] = {}
    all_warnings: List[str] = []

    total_gross = 0.0
    total_reimbursed = 0.0
    total_net = 0.0
    total_computable = 0.0

    for inv in invoices:
        if isinstance(inv, InvoiceData):
            code = inv.suggested_category.value
        else:
            code = inv.get("suggested_category", "GASTOS_EDUCACION")

        current_cum = cumulative_totals.get(code, 0.0)
        res = compute_deduction(
            invoice_data=inv,
            siradig_code=code,
            fiscal_year=fiscal_year,
            cumulative_category_total=current_cum,
            custom_caps=caps
        )

        total_gross += res["gross_amount"]
        total_reimbursed += res["reimbursed_amount"]
        total_net += res["net_out_of_pocket"]
        comp = res["computable_deduction"]
        total_computable += comp

        cumulative_totals[code] = current_cum + comp
        if res.get("warnings"):
            all_warnings.extend(res["warnings"])

        if code not in category_breakdown:
            category_breakdown[code] = {
                "count": 0,
                "gross_total": 0.0,
                "computable_total": 0.0,
                "cap_limit": res.get("applied_annual_cap") or 0.0
            }
        category_breakdown[code]["count"] += 1
        category_breakdown[code]["gross_total"] += res["gross_amount"]
        category_breakdown[code]["computable_total"] += comp

    return AnnualDeductionSummary(
        fiscal_year=fiscal_year,
        total_invoices_evaluated=len(invoices),
        total_gross_amount=round(total_gross, 2),
        total_reimbursed_amount=round(total_reimbursed, 2),
        total_net_of_pocket=round(total_net, 2),
        total_computable_deductions=round(total_computable, 2),
        category_breakdown=category_breakdown,
        applied_caps={k: v.get("cap_limit", 0.0) for k, v in category_breakdown.items()},
        warnings=all_warnings
    )


def generate_siradig_payload(
    taxpayer_cuit: str,
    fiscal_year: int,
    deductions_list: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compiles all validated deductions into the standard JSON format for SiRADIG F.572 Web.
    Implements the 4th tool required by mcp_tools_schema.json.
    """
    payload = {
        "taxpayer_cuit": taxpayer_cuit.replace("-", ""),
        "fiscal_year": fiscal_year,
        "presentation_type": "DRAFT",
        "generated_by": "agente_arca_engine",
        "total_items": len(deductions_list),
        "deductions": []
    }

    for item in deductions_list:
        payload["deductions"].append({
            "siradig_code": item.get("siradig_code", "GASTOS_EDUCACION"),
            "vendor_cuit": item.get("vendor_cuit", ""),
            "receipt_type": item.get("receipt_type", "FACTURA_B"),
            "point_of_sale": item.get("point_of_sale"),
            "receipt_number": item.get("receipt_number"),
            "issue_date": item.get("issue_date", ""),
            "total_amount": float(item.get("total_amount", 0.0)),
            "reimbursed_amount": float(item.get("reimbursed_amount", 0.0)),
            "cae": item.get("cae", ""),
            "cae_due_date": item.get("cae_due_date", ""),
            "beneficiary_cuil": item.get("beneficiary_cuil", ""),
            "computable_deduction": float(item.get("computable_deduction", item.get("total_amount", 0.0)))
        })

    logger.info(f"Generated standard SiRADIG payload with {len(payload['deductions'])} items for CUIT {taxpayer_cuit}.")
    return payload
