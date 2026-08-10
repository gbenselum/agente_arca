"""
Pydantic models for legal validation results.
"""

from pydantic import BaseModel, Field


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING, INFO
    error_code: str | None = None


class ValidationResult(BaseModel):
    is_valid: bool
    invoice_id: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: list[ValidationErrorDetail] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_reason: str | None = None
