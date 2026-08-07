"""
Pydantic models for deduction calculation and annual fiscal caps (RG 4003/17).
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FiscalYearCaps(BaseModel):
    fiscal_year: int
    mni_anual: float = Field(description="Minimo No Imponible Anual (Ganancias)")
    gna_anual: Optional[float] = Field(default=None, description="Ganancia Neta Acumulada Anual (Base imponible previa deducciones)")
    deduccion_especial_anual: Optional[float] = Field(default=None, description="Deduccion Especial Anual")
    notes: Optional[str] = Field(default=None, description="Legal reference notes (e.g. RG AFIP / IPC Updates)")


class DeductionResult(BaseModel):
    invoice_id: str
    siradig_code: str
    gross_amount: float
    reimbursed_amount: float
    net_out_of_pocket: float
    deductible_rate: float
    subtotal_before_cap: float
    applied_annual_cap: Optional[float] = None
    computable_deduction: float
    requires_employer_cap_check: bool = True
    warnings: List[str] = Field(default_factory=list)
    cap_exceeded: bool = False
    cap_limit_description: Optional[str] = None


class AnnualDeductionSummary(BaseModel):
    fiscal_year: int
    total_invoices_evaluated: int
    total_gross_amount: float
    total_reimbursed_amount: float
    total_net_out_of_pocket: float
    total_computable_deductions: float
    category_breakdown: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    applied_caps: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
