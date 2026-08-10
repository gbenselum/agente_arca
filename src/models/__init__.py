"""
Domain models for ARCA / AFIP SiRADIG F.572 Web automation and tax processing.
"""

from .automator import AutomatorBatchResult, AutomatorItemResult
from .deduction import AnnualDeductionSummary, DeductionResult, FiscalYearCaps
from .f572 import DependentModel, F572Data, F572LoadedInvoice
from .invoice import InvoiceData, InvoiceParseResult, ReceiptType, SiRADIGCategory
from .validation import ValidationErrorDetail, ValidationResult

__all__ = [
    "AnnualDeductionSummary",
    "AutomatorBatchResult",
    "AutomatorItemResult",
    "DeductionResult",
    "DependentModel",
    "F572Data",
    "F572LoadedInvoice",
    "FiscalYearCaps",
    "InvoiceData",
    "InvoiceParseResult",
    "ReceiptType",
    "SiRADIGCategory",
    "ValidationErrorDetail",
    "ValidationResult",
]
