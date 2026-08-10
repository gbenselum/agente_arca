"""
Comprehensive validator and integration test suite for ARCA agent.
"""

import os
import unittest
from pathlib import Path

from src.engine.deduction_calculator import compute_deduction
from src.parser.f572_parser import is_invoice_already_in_f572, sync_f572_to_env
from src.validator.legal_validator import validate_cuit, validate_invoice_detailed


class TestARCAValidator(unittest.TestCase):
    def test_validate_cuit_format(self):
        # Mathematically valid CUIT (30711234566)
        self.assertTrue(validate_cuit("30711234566"))
        # Invalid CUIT
        self.assertFalse(validate_cuit("12345678901"))

    def test_validate_invoice_legal_requirements(self):
        invoice = {
            "vendor_cuit": "30711234566",
            "receipt_type": "FACTURA_B",
            "point_of_sale": 4,
            "receipt_number": 12890,
            "issue_date": "2026-03-15",
            "total_amount": 45000.00,
            "reimbursed_amount": 10000.00,
            "beneficiary_cuil": "20456789014",
        }
        dependents = [
            {
                "first_name": "Juan",
                "last_name": "Perez",
                "cuit": "20456789014",
                "relationship": "HIJO",
                "birth_date": "2015-05-10",
            }
        ]

        result = validate_invoice_detailed(invoice, dependents, 2026)
        self.assertTrue(result.is_valid, f"Expected valid invoice, but got errors: {result.errors}")
        self.assertEqual(len(result.errors), 0)

    def test_compute_deduction_medical(self):
        invoice = {"invoice_id": "INV-001", "total_amount": 50000.00, "reimbursed_amount": 10000.00}
        res = compute_deduction(invoice, "MEDICO_PARAMEDICO")
        self.assertEqual(res.net_out_of_pocket, 40000.00)
        self.assertEqual(res.deductible_rate, 0.40)
        self.assertEqual(res.computable_deduction, 16000.00)

    def test_duplicate_check_against_f572(self):
        f572_data = {
            "taxpayer_cuit": "20123456789",
            "fiscal_year": 2026,
            "loaded_invoices": [
                {"vendor_cuit": "30711234567", "point_of_sale": 5, "receipt_number": 12890, "total_amount": 85000.0}
            ],
        }

        duplicate_inv = {
            "vendor_cuit": "30711234567",
            "point_of_sale": 5,
            "receipt_number": 12890,
            "total_amount": 85000.0,
        }
        self.assertTrue(is_invoice_already_in_f572(duplicate_inv, f572_data))

    def test_duplicate_check_by_month_and_amount(self):
        f572_data = {
            "taxpayer_cuit": "20123456789",
            "fiscal_year": 2026,
            "loaded_invoices": [
                {
                    "vendor_cuit": "33611969959",
                    "point_of_sale": None,
                    "receipt_number": None,
                    "total_amount": 424665.74,
                    "month": 3,
                }
            ],
        }

        duplicate_inv = {
            "vendor_cuit": "33611969959",
            "point_of_sale": 1,
            "receipt_number": 4455,
            "total_amount": 424665.74,
            "issue_date": "2026-03-15",
        }
        non_duplicate_inv = {
            "vendor_cuit": "33611969959",
            "point_of_sale": 1,
            "receipt_number": 4456,
            "total_amount": 424665.74,
            "issue_date": "2026-04-15",  # Different month
        }
        self.assertTrue(is_invoice_already_in_f572(duplicate_inv, f572_data))
        self.assertFalse(is_invoice_already_in_f572(non_duplicate_inv, f572_data))

    def test_sync_f572_to_env(self):
        f572_data = {
            "taxpayer_cuit": "20123456789",
            "fiscal_year": 2026,
            "dependents": [{"cuit": "20551234569", "name": "Mateo Perez", "birth_date": "2018-04-12"}],
        }
        test_env_path = "tests/test_temp.env"
        success = sync_f572_to_env(f572_data, test_env_path)
        self.assertTrue(success)
        self.assertTrue(Path(test_env_path).exists())

        # Clean up temporary test env file
        if Path(test_env_path).exists():
            os.remove(test_env_path)


if __name__ == "__main__":
    unittest.main()
