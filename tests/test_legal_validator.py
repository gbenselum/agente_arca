"""
Unit tests for legal validator module across all Argentine CUIT prefixes and RG 4003 rules.
"""

import unittest

from src.models.f572 import DependentModel
from src.models.invoice import InvoiceData, ReceiptType, SiRADIGCategory
from src.validator.legal_validator import validate_cuit, validate_invoice_detailed


class TestLegalValidator(unittest.TestCase):
    def test_cuit_modulo_11_all_prefixes(self):
        # Valid Argentine CUITs with prefixes: 20, 23, 24, 27, 30, 33, 34
        valid_cuits = [
            "20123456786",  # 20
            "27123456780",  # 27
            "30711234566",  # 30
            "33611969959",  # 33
            "23123456785",  # 23
            "24123456781",  # 24
        ]
        for cuit in valid_cuits:
            self.assertTrue(validate_cuit(cuit), f"Expected valid CUIT: {cuit}")

        # Invalid CUITs
        invalid_cuits = [
            "12345678901",  # Invalid prefix 12
            "20123456789",  # Wrong checksum
            "30711234560",  # Wrong checksum
            "abc12345678",  # Non-numeric
            "20123",  # Too short
        ]
        for cuit in invalid_cuits:
            self.assertFalse(validate_cuit(cuit), f"Expected invalid CUIT: {cuit}")

    def test_education_dependent_age_limit(self):
        # Beneficiary older than 24 years old (using valid CUIT 20456789014)
        invoice = InvoiceData(
            vendor_cuit="30711234566",
            receipt_type=ReceiptType.FACTURA_B,
            point_of_sale=1,
            receipt_number=100,
            issue_date="2026-05-10",
            total_amount=50000.0,
            beneficiary_cuil="20456789014",
            suggested_category=SiRADIGCategory.GASTOS_EDUCACION,
        )
        dependents = [
            DependentModel(
                first_name="Adult",
                last_name="Child",
                cuit="20456789014",
                birth_date="1998-01-01",  # Age 28 in 2026 (> 24)
            )
        ]
        res = validate_invoice_detailed(invoice, dependents, 2026)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("24" in err for err in res.errors))

    def test_unregistered_beneficiary_fails(self):
        invoice = InvoiceData(
            vendor_cuit="30711234566",
            receipt_type=ReceiptType.FACTURA_B,
            point_of_sale=1,
            receipt_number=100,
            issue_date="2026-05-10",
            total_amount=50000.0,
            beneficiary_cuil="20123456786",  # Not in dependents
            suggested_category=SiRADIGCategory.GASTOS_EDUCACION,
        )
        dependents = [
            DependentModel(first_name="Mateo", last_name="Perez", cuit="20551234569", birth_date="2018-04-12")
        ]
        res = validate_invoice_detailed(invoice, dependents, 2026)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("not registered" in err.lower() for err in res.errors))


if __name__ == "__main__":
    unittest.main()
