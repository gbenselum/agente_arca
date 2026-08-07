"""
Pydantic models for Playwright browser automation results.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AutomatorItemResult(BaseModel):
    siradig_code: str
    invoice_id: str
    status: str = "DRAFT_SAVED"  # DRAFT_SAVED, SKIPPED, FAILED
    category_name: str = ""
    point_of_sale: Optional[int] = None
    receipt_number: Optional[int] = None
    amount: float = 0.0
    screenshot_path: Optional[str] = None
    error: Optional[str] = None


class AutomatorBatchResult(BaseModel):
    success: bool
    fiscal_year: int
    processed_count: int = 0
    saved_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: List[AutomatorItemResult] = Field(default_factory=list)
    message: str = ""
    error: Optional[str] = None
    session_screenshots: List[str] = Field(default_factory=list)
    execution_time_seconds: float = 0.0
