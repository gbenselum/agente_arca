"""
CLI integration tests: exercise main.collect_validated_invoices and cmd_validate_and_compute
with real temp directories and sample JSON files (no browser involved).
"""

import argparse
import json
import os
import tempfile
import unittest
from unittest import mock

import main
from main import cmd_upload_draft, cmd_validate_and_compute, collect_validated_invoices

# Modulo-11-valid sample CUITs (see .env.example)
TAXPAYER_CUIT = "20780009188"
VENDOR_COLEGIO = "30117368544"
VENDOR_MEDICA = "30200798909"
BENEFICIARY_LUCIA = "27042489943"


def _invoice_json(vendor_cuit: str, pos: int, num: int, amount: float, category: str) -> dict:
    return {
        "vendor_cuit": vendor_cuit,
        "vendor_name": "Test Vendor",
        "receipt_type": "FACTURA_B",
        "point_of_sale": pos,
        "receipt_number": num,
        "issue_date": "2026-03-15",
        "total_amount": amount,
        "reimbursed_amount": 0.0,
        "cae": "74123456789012",
        "cae_due_date": "2026-03-25",
        "beneficiary_cuil": "",
        "suggested_category": category,
        "extraction_method": "test",
    }


def _write_json(directory: str, filename: str, data: dict) -> str:
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


class TestCliIntegration(unittest.TestCase):
    def _make_args(
        self, vp_dir: str, inv_dir: str, fiscal_year: int = 2026, headless: bool = False
    ) -> argparse.Namespace:
        return argparse.Namespace(
            vistaprevia_dir=vp_dir,
            invoices_dir=inv_dir,
            fiscal_year=fiscal_year,
            output_json=None,
            headless=headless,
            upload_draft=False,
        )

    def test_collect_validated_filters_duplicates_and_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp_dir = os.path.join(tmp, "vistaprevia")
            inv_dir = os.path.join(tmp, "invoices")
            os.makedirs(vp_dir)
            os.makedirs(inv_dir)

            # F.572 export already contains invoice 30117368544-0004-12890.
            _write_json(
                vp_dir,
                "F572_2026.json",
                {
                    "taxpayer_cuit": TAXPAYER_CUIT,
                    "fiscal_year": 2026,
                    "loaded_invoices": [
                        {
                            "vendor_cuit": VENDOR_COLEGIO,
                            "point_of_sale": 4,
                            "receipt_number": 12890,
                            "total_amount": 145250.50,
                        }
                    ],
                },
            )

            # 1) duplicate of the loaded invoice -> must be skipped
            _write_json(
                inv_dir, "duplicate.json", _invoice_json(VENDOR_COLEGIO, 4, 12890, 145250.50, "GASTOS_EDUCACION")
            )
            # 2) a valid new invoice -> must pass
            _write_json(
                inv_dir, "new_colegio.json", _invoice_json(VENDOR_COLEGIO, 4, 12891, 90000.00, "GASTOS_EDUCACION")
            )
            # 3) invoice with invalid CUIT -> must be filtered out by legal validation
            _write_json(inv_dir, "bad_cuit.json", _invoice_json("30999999999", 4, 12892, 50000.00, "GASTOS_EDUCACION"))

            args = self._make_args(vp_dir, inv_dir)
            valid = collect_validated_invoices(args, verbose=False)

            self.assertEqual(len(valid), 1)
            self.assertEqual(valid[0]["receipt_number"], 12891)

    def test_cmd_validate_and_compute_writes_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp_dir = os.path.join(tmp, "vistaprevia")
            inv_dir = os.path.join(tmp, "invoices")
            out_json = os.path.join(tmp, "summary.json")
            os.makedirs(vp_dir)
            os.makedirs(inv_dir)

            _write_json(inv_dir, "colegio.json", _invoice_json(VENDOR_COLEGIO, 4, 12900, 120000.00, "GASTOS_EDUCACION"))
            _write_json(inv_dir, "medica.json", _invoice_json(VENDOR_MEDICA, 1, 555, 50000.00, "MEDICO_PARAMEDICO"))

            args = self._make_args(vp_dir, inv_dir)
            args.output_json = out_json
            rc = cmd_validate_and_compute(args)

            self.assertEqual(rc, 0)
            with open(out_json, encoding="utf-8") as f:
                summary = json.load(f)
            self.assertEqual(summary["total_invoices_evaluated"], 2)
            self.assertIn("GASTOS_EDUCACION", summary["category_breakdown"])
            self.assertIn("MEDICO_PARAMEDICO", summary["category_breakdown"])

    def test_no_eligible_invoices_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            vp_dir = os.path.join(tmp, "vistaprevia")
            inv_dir = os.path.join(tmp, "invoices")
            os.makedirs(vp_dir)
            os.makedirs(inv_dir)

            # Only an invalid invoice (bad CUIT) present.
            _write_json(inv_dir, "bad.json", _invoice_json("30999999999", 4, 999, 100.00, "GASTOS_EDUCACION"))

            args = self._make_args(vp_dir, inv_dir)
            rc = cmd_validate_and_compute(args)
            self.assertEqual(rc, 0)

    def test_cmd_upload_draft_is_single_step(self):
        """upload-draft must NOT re-run sync/parse/validate steps (single-step command)."""
        with tempfile.TemporaryDirectory() as tmp:
            vp_dir = os.path.join(tmp, "vistaprevia")
            inv_dir = os.path.join(tmp, "invoices")
            os.makedirs(vp_dir)
            os.makedirs(inv_dir)
            _write_json(inv_dir, "colegio.json", _invoice_json(VENDOR_COLEGIO, 4, 13000, 90000.00, "GASTOS_EDUCACION"))

            args = self._make_args(vp_dir, inv_dir)

            with (
                mock.patch.object(main, "cmd_sync_f572") as mock_sync,
                mock.patch.object(main, "cmd_parse_invoices") as mock_parse,
                mock.patch.object(main, "cmd_validate_and_compute") as mock_validate,
                mock.patch.object(main.SiRADIGAutomator, "run_draft_upload") as mock_upload,
            ):
                mock_upload.return_value = mock.MagicMock(success=True, saved_count=1, processed_count=1, error=None)
                rc = cmd_upload_draft(args)

            self.assertEqual(rc, 0)
            mock_sync.assert_not_called()
            mock_parse.assert_not_called()
            mock_validate.assert_not_called()
            # Upload receives exactly the validated, non-duplicate subset (1 invoice here).
            self.assertEqual(mock_upload.call_count, 1)
            uploaded = mock_upload.call_args.kwargs["deductions"]
            self.assertEqual(len(uploaded), 1)
            self.assertEqual(uploaded[0]["receipt_number"], 13000)

    def test_cmd_upload_draft_skips_when_no_valid_invoices(self):
        """upload-draft with only invalid invoices must skip the browser entirely."""
        with tempfile.TemporaryDirectory() as tmp:
            vp_dir = os.path.join(tmp, "vistaprevia")
            inv_dir = os.path.join(tmp, "invoices")
            os.makedirs(vp_dir)
            os.makedirs(inv_dir)
            _write_json(inv_dir, "bad.json", _invoice_json("30999999999", 4, 999, 100.00, "GASTOS_EDUCACION"))

            args = self._make_args(vp_dir, inv_dir)

            with mock.patch.object(main.SiRADIGAutomator, "run_draft_upload") as mock_upload:
                rc = cmd_upload_draft(args)

            self.assertEqual(rc, 0)
            mock_upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
