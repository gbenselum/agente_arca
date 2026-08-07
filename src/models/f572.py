"""
Pydantic models for F.572 Vista Previa exports and registered dependents.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import re


class DependentModel(BaseModel):
    first_name: str = Field(default="", description="Dependent's first name")
    last_name: str = Field(default="", description="Dependent's last name")
    cuit: str = Field(default="", description="11-digit CUIT/CUIL without dashes")
    relationship: str = Field(default="HIJO", description="Relationship: HIJO, HIJA, CONYUGE, etc.")
    birth_date: str = Field(default="", description="Birth date in YYYY-MM-DD format")
    percentage: int = Field(default=100, ge=1, le=100, description="Deduction percentage share")

    @field_validator("cuit", mode="before")
    @classmethod
    def clean_cuit(cls, v):
        if isinstance(v, str):
            return re.sub(r"\D", "", v)
        return "" if v is None else str(v)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class F572LoadedInvoice(BaseModel):
    vendor_cuit: str = Field(default="", description="Vendor CUIT without dashes")
    vendor_name: Optional[str] = Field(default="", description="Vendor name if available")
    point_of_sale: Optional[int] = Field(default=None, description="Punto de Venta")
    receipt_number: Optional[int] = Field(default=None, description="Numero de Comprobante")
    total_amount: float = Field(default=0.0, description="Loaded amount in F.572")
    month: Optional[int] = Field(default=None, ge=1, le=12, description="Month of monthly aggregated expense")
    category: Optional[str] = Field(default=None, description="Category in F.572")
    dependent_cuit: Optional[str] = Field(default=None, description="Dependent CUIT if linked")
    dependent_name: Optional[str] = Field(default=None, description="Dependent name if linked")

    @field_validator("vendor_cuit", "dependent_cuit", mode="before")
    @classmethod
    def clean_cuit(cls, v):
        if isinstance(v, str):
            return re.sub(r"\D", "", v)
        return "" if v is None else str(v)


class F572Data(BaseModel):
    taxpayer_cuit: str = Field(default="", description="Taxpayer CUIL / CUIT")
    taxpayer_name: str = Field(default="", description="Taxpayer Full Legal Name")
    fiscal_year: Optional[int] = Field(default=None, description="Fiscal year (e.g. 2026)")
    presentation_date: str = Field(default="", description="Export or presentation date")
    dependents: List[DependentModel] = Field(default_factory=list, description="Registered family dependents")
    loaded_invoices: List[F572LoadedInvoice] = Field(default_factory=list, description="Already loaded invoices in F.572")
    source_pdf: Optional[str] = Field(default=None, description="Source PDF path")

    @field_validator("taxpayer_cuit", mode="before")
    @classmethod
    def clean_cuit(cls, v):
        if isinstance(v, str):
            return re.sub(r"\D", "", v)
        return "" if v is None else str(v)
