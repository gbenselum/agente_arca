"""
Pydantic models for legal validation results.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    error_code: Optional[str] = None


class ValidationResult(BaseModel):
    is_valid: bool
    invoice_id: str = ""
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    details: List[ValidationErrorDetail] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_reason: Optional[str] = None
