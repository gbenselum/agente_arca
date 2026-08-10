"""
Pydantic models for Playwright browser automation results.
"""

from pydantic import BaseModel, Field


class AutomatorItemResult(BaseModel):
    siradig_code: str
    invoice_id: str
    status: str = "DRAFT_SAVED"  # DRAFT_SAVED, FAILED
    category_name: str = ""
    point_of_sale: int | None = None
    receipt_number: int | None = None
    amount: float = 0.0
    screenshot_path: str | None = None
    error: str | None = None


class AutomatorBatchResult(BaseModel):
    success: bool
    fiscal_year: int
    processed_count: int = 0
    saved_count: int = 0
    failed_count: int = 0
    items: list[AutomatorItemResult] = Field(default_factory=list)
    message: str = ""
    error: str | None = None
    session_screenshots: list[str] = Field(default_factory=list)
    execution_time_seconds: float = 0.0
