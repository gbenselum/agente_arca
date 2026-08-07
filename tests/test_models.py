"""
Unit tests for Pydantic models in src/models/.
"""

import unittest
from src.models.invoice import InvoiceData, ReceiptType, SiRADIGCategory
from src.models.f572 import DependentModel, F572LoadedInvoice, F572Data
from src.models.deduction import FiscalYearCaps, DeductionResult


class TestModels(unittest.TestCase):
    def test_invoice_model_cleaning_and_id(self):
        inv = InvoiceData(
            vendor_cuit="30-71123456-6",
            point_of_sale=4,
            receipt_number=12890,
            total_amount=45000.50,
            suggested_category=SiRADIGCategory.GASTOS_EDUCACION
        )
        self.assertEqual(inv.vendor_cuit, "30711234566")
        self.assertEqual(inv.invoice_id, "30711234566-0004-00012890")

    def test_dependent_model_full_name(self):
        dep = DependentModel(
            first_name="Mateo",
            last_name="Perez",
            cuit="20-55123456-9",
            birth_date="2018-04-12"
        )
        self.assertEqual(dep.cuit, "20551234569")
        self.assertEqual(dep.full_name, "Mateo Perez")

    def test_f572_data_model(self):
        data = F572Data(
            taxpayer_cuit="20-12345678-9",
            taxpayer_name="Juan Perez",
            fiscal_year=2026
        )
        self.assertEqual(data.taxpayer_cuit, "20123456789")
        self.assertEqual(data.fiscal_year, 2026)


if __name__ == "__main__":
    unittest.main()
