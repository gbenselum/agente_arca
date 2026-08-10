"""
Unit tests for F.572 parser, safe env updates, and duplicate detection.
"""

import os
import unittest

from src.models.f572 import DependentModel, F572Data
from src.parser.f572_parser import is_invoice_already_in_f572, sync_f572_to_env


class TestF572Parser(unittest.TestCase):
    def test_non_destructive_env_sync(self):
        test_env_path = "tests/test_non_destructive.env"
        # Write initial .env with comments and custom variables
        with open(test_env_path, "w", encoding="utf-8") as f:
            f.write("# User custom comment\n")
            f.write("CUSTOM_VAR=keep_me\n")
            f.write("BROWSER_HEADLESS=false\n")

        f572_data = F572Data(
            taxpayer_cuit="20123456789",
            taxpayer_name="Juan Perez",
            fiscal_year=2026,
            dependents=[DependentModel(first_name="Mateo", last_name="Perez", cuit="20551234569")],
        )

        success = sync_f572_to_env(f572_data, env_file_path=test_env_path)
        self.assertTrue(success)

        # Read back and verify custom comment and custom var are still present
        with open(test_env_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn("CUSTOM_VAR=keep_me", content)
        self.assertIn("BROWSER_HEADLESS=false", content)
        self.assertIn("ARCA_CUIL=20123456789", content)
        self.assertIn("DEPENDENT_1_CUIT=20551234569", content)

        if os.path.exists(test_env_path):
            os.remove(test_env_path)

    def test_duplicate_check_logic(self):
        f572_data = F572Data(
            taxpayer_cuit="20123456789",
            fiscal_year=2026,
            loaded_invoices=[
                {"vendor_cuit": "30711234566", "point_of_sale": 4, "receipt_number": 12890, "total_amount": 45000.00}
            ],
        )
        duplicate = {
            "vendor_cuit": "30-71123456-6",
            "point_of_sale": 4,
            "receipt_number": 12890,
            "total_amount": 45000.00,
        }
        non_duplicate = {
            "vendor_cuit": "30-71123456-6",
            "point_of_sale": 4,
            "receipt_number": 12891,
            "total_amount": 45000.00,
        }
        self.assertTrue(is_invoice_already_in_f572(duplicate, f572_data))
        self.assertFalse(is_invoice_already_in_f572(non_duplicate, f572_data))


if __name__ == "__main__":
    unittest.main()
