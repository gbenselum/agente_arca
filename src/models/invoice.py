"""
Pydantic models for invoice representation, extraction, and categories.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class ReceiptType(str, Enum):
    FACTURA_A = "FACTURA_A"
    FACTURA_B = "FACTURA_B"
    FACTURA_C = "FACTURA_C"
    FACTURA_M = "FACTURA_M"
    FACTURA_E = "FACTURA_E"
    NOTA_DE_DEBITO_A = "NOTA_DE_DEBITO_A"
    NOTA_DE_DEBITO_B = "NOTA_DE_DEBITO_B"
    NOTA_DE_DEBITO_C = "NOTA_DE_DEBITO_C"
    NOTA_DE_CREDITO_A = "NOTA_DE_CREDITO_A"
    NOTA_DE_CREDITO_B = "NOTA_DE_CREDITO_B"
    NOTA_DE_CREDITO_C = "NOTA_DE_CREDITO_C"
    RECIBO_B = "RECIBO_B"
    RECIBO_C = "RECIBO_C"
    TICKET_FACTURA = "TICKET_FACTURA"
    VEP_DOMESTICO = "VEP_DOMESTICO"
    UNKNOWN = "UNKNOWN"


class SiRADIGCategory(str, Enum):
    GASTOS_EDUCACION = "GASTOS_EDUCACION"
    MEDICO_PARAMEDICO = "MEDICO_PARAMEDICO"
    CUOTA_MEDICO_ASSIST = "CUOTA_MEDICO_ASSIST"
    ALQUILER_HABITACION = "ALQUILER_HABITACION"
    ALQUILER_ADICIONAL_10 = "ALQUILER_ADICIONAL_10"
    CASAS_PARTICULARES = "CASAS_PARTICULARES"
    INTERES_HIPOTECARIO = "INTERES_HIPOTECARIO"
    DONACIONES = "DONACIONES"
    SEGUROS_VIDA_RETIRO = "SEGUROS_VIDA_RETIRO"
    GASTOS_SEPELIO = "GASTOS_SEPELIO"


class InvoiceData(BaseModel):
    vendor_cuit: str = Field(default="", description="CUIT of issuing vendor without dashes")
    vendor_name: str = Field(default="", description="Legal business or professional name")
    receipt_type: ReceiptType = Field(default=ReceiptType.FACTURA_B, description="AFIP receipt classification")
    point_of_sale: Optional[int] = Field(default=None, description="Punto de Venta (1-5 digits)")
    receipt_number: Optional[int] = Field(default=None, description="Numero de Comprobante (1-8 digits)")
    issue_date: str = Field(default="", description="Issue date in YYYY-MM-DD format")
    total_amount: float = Field(default=0.0, ge=0.0, description="Gross total invoice amount in ARS")
    reimbursed_amount: float = Field(default=0.0, ge=0.0, description="Amount already reimbursed by health plan or employer")
    cae: str = Field(default="", description="14-digit CAE or CAEA authorization code")
    cae_due_date: str = Field(default="", description="CAE expiration date in YYYY-MM-DD")
    concept_description: str = Field(default="", description="Invoice description / line item details")
    beneficiary_cuil: str = Field(default="", description="CUIT/CUIL of the family dependent or taxpayer benefiting from expense")
    suggested_category: SiRADIGCategory = Field(default=SiRADIGCategory.GASTOS_EDUCACION, description="Mapped SiRADIG category key")
    source_pdf: Optional[str] = Field(default=None, description="Source PDF filename")
    extraction_method: str = Field(default="pypdf", description="Method used for extraction: pypdf, ocr, manual")
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score of the extraction")

    @field_validator("vendor_cuit", "beneficiary_cuil", mode="before")
    @classmethod
    def clean_cuit(cls, v):
        if isinstance(v, str):
            return re.sub(r"\D", "", v)
        return "" if v is None else str(v)

    @property
    def invoice_id(self) -> str:
        pos = f"{self.point_of_sale:04d}" if self.point_of_sale is not None else "0000"
        num = f"{self.receipt_number:08d}" if self.receipt_number is not None else "00000000"
        return f"{self.vendor_cuit}-{pos}-{num}"


class InvoiceParseResult(BaseModel):
    success: bool
    invoice: Optional[InvoiceData] = None
    raw_text: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    file_path: str = ""
