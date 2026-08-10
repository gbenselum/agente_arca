"""
Unit tests for deduction calculation, RG 4003/17 annual caps, and SiRADIG payload generator.
"""

import unittest

from src.engine.deduction_calculator import (
    ESTIMATED_CAP_YEARS,
    FiscalYearCaps,
    compute_batch_deductions,
    compute_deduction,
    generate_siradig_payload,
    get_fiscal_caps,
)


class TestDeductionCalculator(unittest.TestCase):
    def test_education_annual_cap_enforcement(self):
        # 2026 MNI is $5,500,000. 40% of MNI is $2,200,000.
        custom_caps = FiscalYearCaps(fiscal_year=2026, mni_anual=5500000.00, gna_anual=30000000.00)

        # Invoice below cap
        inv1 = {"invoice_id": "INV-001", "total_amount": 100000.00, "reimbursed_amount": 0.0}
        res1 = compute_deduction(
            inv1, "GASTOS_EDUCACION", fiscal_year=2026, cumulative_category_total=0.0, custom_caps=custom_caps
        )
        self.assertEqual(res1.computable_deduction, 100000.00)
        self.assertFalse(res1.cap_exceeded)

        # Invoice exceeding remaining cap
        # Remaining cap is 2,200,000 - 2,150,000 = 50,000
        inv2 = {"invoice_id": "INV-002", "total_amount": 120000.00, "reimbursed_amount": 0.0}
        res2 = compute_deduction(
            inv2, "GASTOS_EDUCACION", fiscal_year=2026, cumulative_category_total=2150000.00, custom_caps=custom_caps
        )
        self.assertEqual(res2.computable_deduction, 50000.00)
        self.assertTrue(res2.cap_exceeded)
        self.assertEqual(len(res2.warnings), 1)

    def test_medical_gna_cap_and_rate(self):
        # Medical deduction is 40% of net out of pocket, capped at 5% of GNA
        custom_caps = FiscalYearCaps(
            fiscal_year=2026, mni_anual=5000000.00, gna_anual=20000000.00
        )  # 5% of 20M = 1,000,000

        inv = {
            "invoice_id": "INV-MED-01",
            "total_amount": 50000.00,
            "reimbursed_amount": 10000.00,  # Net = 40,000 * 40% = 16,000
        }
        res = compute_deduction(inv, "MEDICO_PARAMEDICO", fiscal_year=2026, custom_caps=custom_caps)
        self.assertEqual(res.net_out_of_pocket, 40000.00)
        self.assertEqual(res.deductible_rate, 0.40)
        self.assertEqual(res.computable_deduction, 16000.00)

    def test_generate_siradig_payload_structure(self):
        deductions = [
            {
                "siradig_code": "GASTOS_EDUCACION",
                "vendor_cuit": "30711234566",
                "receipt_type": "FACTURA_B",
                "point_of_sale": 4,
                "receipt_number": 12890,
                "issue_date": "2026-03-15",
                "total_amount": 45000.00,
                "reimbursed_amount": 0.0,
                "computable_deduction": 45000.00,
            }
        ]
        payload = generate_siradig_payload("20-12345678-9", 2026, deductions)
        self.assertEqual(payload["taxpayer_cuit"], "20123456789")
        self.assertEqual(payload["fiscal_year"], 2026)
        self.assertEqual(len(payload["deductions"]), 1)
        self.assertEqual(payload["deductions"][0]["computable_deduction"], 45000.00)

    def test_compute_batch_deductions_end_to_end(self):
        """Regression test: batch computation must not crash and must aggregate correctly.

        Guards against the `total_net_of_pocket` / `total_net_out_of_pocket` keyword
        mismatch that raised a Pydantic ValidationError for every batch.
        """
        invoices = [
            {
                "invoice_id": "BATCH-001",
                "vendor_cuit": "30711234566",
                "point_of_sale": 4,
                "receipt_number": 12890,
                "total_amount": 100000.00,
                "reimbursed_amount": 0.0,
                "suggested_category": "GASTOS_EDUCACION",
            },
            {
                "invoice_id": "BATCH-002",
                "vendor_cuit": "30711234566",
                "point_of_sale": 4,
                "receipt_number": 12891,
                "total_amount": 50000.00,
                "reimbursed_amount": 10000.00,  # Net 40,000 * 40% = 16,000
                "suggested_category": "MEDICO_PARAMEDICO",
            },
            {
                "invoice_id": "BATCH-003",
                "vendor_cuit": "30711234566",
                "point_of_sale": 4,
                "receipt_number": 12892,
                "total_amount": 20000.00,
                "reimbursed_amount": 0.0,
                "suggested_category": "GASTOS_EDUCACION",
            },
        ]

        summary = compute_batch_deductions(invoices, fiscal_year=2026)

        self.assertEqual(summary.fiscal_year, 2026)
        self.assertEqual(summary.total_invoices_evaluated, 3)
        self.assertEqual(summary.total_gross_amount, 170000.00)
        self.assertEqual(summary.total_reimbursed_amount, 10000.00)
        self.assertEqual(summary.total_net_out_of_pocket, 160000.00)
        # GASTOS_EDUCACION: 100k + 20k = 120k | MEDICO_PARAMEDICO: 40k * 0.4 = 16k
        self.assertEqual(summary.total_computable_deductions, 136000.00)
        self.assertEqual(summary.category_breakdown["GASTOS_EDUCACION"]["count"], 2)
        self.assertEqual(summary.category_breakdown["MEDICO_PARAMEDICO"]["count"], 1)
        self.assertEqual(summary.category_breakdown["MEDICO_PARAMEDICO"]["computable_total"], 16000.00)

    def test_compute_batch_deductions_cumulative_cap(self):
        """Cumulative annual cap enforcement across a batch (education 40% of MNI)."""
        custom_caps = FiscalYearCaps(fiscal_year=2026, mni_anual=5500000.00, gna_anual=30000000.00)
        # Education cap = 40% * 5.5M = 2,200,000. Two invoices crossing the cap.
        invoices = [
            {
                "invoice_id": "CAP-001",
                "total_amount": 2100000.00,
                "reimbursed_amount": 0.0,
                "suggested_category": "GASTOS_EDUCACION",
            },
            {
                "invoice_id": "CAP-002",
                "total_amount": 500000.00,
                "reimbursed_amount": 0.0,
                "suggested_category": "GASTOS_EDUCACION",
            },
        ]
        summary = compute_batch_deductions(invoices, fiscal_year=2026, custom_caps=custom_caps)

        # First invoice fully computable (2.1M < 2.2M), second truncated to remaining 100k.
        self.assertEqual(summary.total_computable_deductions, 2200000.00)
        self.assertEqual(len(summary.warnings), 1)
        self.assertEqual(summary.applied_caps["GASTOS_EDUCACION"], 2200000.00)

    def test_estimated_cap_years_emit_warning(self):
        """get_fiscal_caps must warn for years with estimated (non-official) caps."""
        # Official year: no estimated-cap warning expected.
        caps_2024 = get_fiscal_caps(2024)
        self.assertEqual(caps_2024.mni_anual, 3091035.00)

        # Estimated years must be flagged in the registry.
        self.assertIn(2025, ESTIMATED_CAP_YEARS)
        self.assertIn(2026, ESTIMATED_CAP_YEARS)

        # A real warning is logged when estimated caps are requested.
        with self.assertLogs("agente_arca", level="WARNING") as ctx:
            get_fiscal_caps(2026)
        self.assertTrue(any("ESTIMATED" in line for line in ctx.output))


if __name__ == "__main__":
    unittest.main()
