"""
Unit tests for deduction calculation, RG 4003/17 annual caps, and SiRADIG payload generator.
"""

import unittest
from src.engine.deduction_calculator import compute_deduction, compute_batch_deductions, generate_siradig_payload, FiscalYearCaps
from src.models.invoice import InvoiceData, SiRADIGCategory


class TestDeductionCalculator(unittest.TestCase):
    def test_education_annual_cap_enforcement(self):
        # 2026 MNI is $5,500,000. 40% of MNI is $2,200,000.
        custom_caps = FiscalYearCaps(fiscal_year=2026, mni_anual=5500000.00, gna_anual=30000000.00)

        # Invoice below cap
        inv1 = {
            "invoice_id": "INV-001",
            "total_amount": 100000.00,
            "reimbursed_amount": 0.0
        }
        res1 = compute_deduction(inv1, "GASTOS_EDUCACION", fiscal_year=2026, cumulative_category_total=0.0, custom_caps=custom_caps)
        self.assertEqual(res1["computable_deduction"], 100000.00)
        self.assertFalse(res1["cap_exceeded"])

        # Invoice exceeding remaining cap
        # Remaining cap is 2,200,000 - 2,150,000 = 50,000
        inv2 = {
            "invoice_id": "INV-002",
            "total_amount": 120000.00,
            "reimbursed_amount": 0.0
        }
        res2 = compute_deduction(inv2, "GASTOS_EDUCACION", fiscal_year=2026, cumulative_category_total=2150000.00, custom_caps=custom_caps)
        self.assertEqual(res2["computable_deduction"], 50000.00)
        self.assertTrue(res2["cap_exceeded"])
        self.assertEqual(len(res2["warnings"]), 1)

    def test_medical_gna_cap_and_rate(self):
        # Medical deduction is 40% of net out of pocket, capped at 5% of GNA
        custom_caps = FiscalYearCaps(fiscal_year=2026, mni_anual=5000000.00, gna_anual=20000000.00)  # 5% of 20M = 1,000,000

        inv = {
            "invoice_id": "INV-MED-01",
            "total_amount": 50000.00,
            "reimbursed_amount": 10000.00  # Net = 40,000 * 40% = 16,000
        }
        res = compute_deduction(inv, "MEDICO_PARAMEDICO", fiscal_year=2026, custom_caps=custom_caps)
        self.assertEqual(res["net_out_of_pocket"], 40000.00)
        self.assertEqual(res["deductible_rate"], 0.40)
        self.assertEqual(res["computable_deduction"], 16000.00)

    def test_generate_siradig_payload_structure(self):
        deductions = [{
            "siradig_code": "GASTOS_EDUCACION",
            "vendor_cuit": "30711234566",
            "receipt_type": "FACTURA_B",
            "point_of_sale": 4,
            "receipt_number": 12890,
            "issue_date": "2026-03-15",
            "total_amount": 45000.00,
            "reimbursed_amount": 0.0,
            "computable_deduction": 45000.00
        }]
        payload = generate_siradig_payload("20-12345678-9", 2026, deductions)
        self.assertEqual(payload["taxpayer_cuit"], "20123456789")
        self.assertEqual(payload["fiscal_year"], 2026)
        self.assertEqual(len(payload["deductions"]), 1)
        self.assertEqual(payload["deductions"][0]["computable_deduction"], 45000.00)


if __name__ == "__main__":
    unittest.main()
