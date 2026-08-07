"""
Domain models for ARCA / AFIP SiRADIG F.572 Web automation and tax processing.
"""

from .invoice import InvoiceData, InvoiceParseResult, ReceiptType, SiRADIGCategory
from .f572 import DependentModel, F572LoadedInvoice, F572Data
from .validation import ValidationResult, ValidationErrorDetail
from .deduction import DeductionResult, FiscalYearCaps, AnnualDeductionSummary
from .automator import AutomatorItemResult, AutomatorBatchResult

__all__ = [
    "InvoiceData",
    "InvoiceParseResult",
    "ReceiptType",
    "SiRADIGCategory",
    "DependentModel",
    "F572LoadedInvoice",
    "F572Data",
    "ValidationResult",
    "ValidationErrorDetail",
    "DeductionResult",
    "FiscalYearCaps",
    "AnnualDeductionSummary",
    "AutomatorItemResult",
    "AutomatorBatchResult",
]
