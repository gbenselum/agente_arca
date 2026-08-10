"""
Unit tests for the SiRADIG Playwright automator with a mocked browser.

These tests exercise the orchestration logic (credential checks, category routing,
UNKNOWN rejection, batch result accounting) without launching a real browser.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from src.browser.siradig_automator import SiRADIGAutomator
from src.models.invoice import InvoiceData, SiRADIGCategory


def _valid_invoice_dict(category: str = "GASTOS_EDUCACION") -> dict:
    return {
        "vendor_cuit": "30117368544",
        "point_of_sale": 4,
        "receipt_number": 12890,
        "issue_date": "2026-03-15",
        "total_amount": 145250.50,
        "receipt_type": "FACTURA_B",
        "suggested_category": category,
        "beneficiary_cuil": "",
    }


class TestSiRADIGAutomator(unittest.TestCase):
    def _make_automator(self, cuil: str = "20780009188", clave: str = "secret123") -> SiRADIGAutomator:
        return SiRADIGAutomator(cuil=cuil, clave_fiscal=clave, headless=True, slow_mo=0)

    @mock.patch("src.browser.siradig_automator.sync_playwright", None)
    def test_missing_playwright_returns_error(self):
        res = self._make_automator().run_draft_upload(fiscal_year=2026, deductions=[_valid_invoice_dict()])
        self.assertFalse(res.success)
        self.assertIn("Playwright is not installed", res.error)

    @mock.patch("src.browser.siradig_automator.sync_playwright")
    def test_missing_credentials_returns_error(self, _mock_pw):
        automator = self._make_automator(cuil="", clave="")
        res = automator.run_draft_upload(fiscal_year=2026, deductions=[_valid_invoice_dict()])
        self.assertFalse(res.success)
        self.assertIn("Missing CUIL or Clave Fiscal", res.error)

    @mock.patch("src.browser.siradig_automator.sync_playwright")
    def test_unknown_category_rejected(self, mock_pw):
        """UNKNOWN categories must fail the item, never be filed as education."""
        page = mock.MagicMock()
        new_page_info = SimpleNamespace(value=page)
        context = mock.MagicMock()
        context.new_page.return_value = page
        context.expect_page.return_value.__enter__.return_value = new_page_info
        browser = mock.MagicMock()
        browser.new_context.return_value = context
        session = mock.MagicMock()
        session.chromium.launch.return_value = browser
        mock_pw.return_value.__enter__.return_value = session

        item = _valid_invoice_dict(category=SiRADIGCategory.UNKNOWN.value)
        res = self._make_automator().run_draft_upload(fiscal_year=2026, deductions=[item])

        self.assertEqual(res.failed_count, 1)
        self.assertEqual(res.saved_count, 0)
        self.assertFalse(res.success)
        self.assertEqual(res.items[0].status, "FAILED")
        self.assertIn("UNKNOWN", res.items[0].error)
        # The education form must never be reached for an unknown category.
        click_args = [c.args for c in page.click.call_args_list]
        self.assertNotIn(("text=Gastos de Educación",), click_args)
        self.assertNotIn(("input[value='Alta de Comprobante']",), click_args)

    @mock.patch("src.browser.siradig_automator.sync_playwright")
    def test_valid_education_item_saves_draft(self, mock_pw):
        page = mock.MagicMock()
        new_page_info = SimpleNamespace(value=page)
        context = mock.MagicMock()
        context.new_page.return_value = page
        context.expect_page.return_value.__enter__.return_value = new_page_info
        browser = mock.MagicMock()
        browser.new_context.return_value = context
        session = mock.MagicMock()
        session.chromium.launch.return_value = browser
        mock_pw.return_value.__enter__.return_value = session

        item = _valid_invoice_dict(category="GASTOS_EDUCACION")
        res = self._make_automator().run_draft_upload(fiscal_year=2026, deductions=[item])

        self.assertTrue(res.success)
        self.assertEqual(res.saved_count, 1)
        self.assertEqual(res.failed_count, 0)
        self.assertEqual(res.items[0].status, "DRAFT_SAVED")
        # Guardrail: only "Guardar" is ever clicked, never a "Finalizar/Confirmar" submit.
        page.click.assert_any_call("input[value='Guardar']", timeout=6000)

    @mock.patch("src.browser.siradig_automator.sync_playwright")
    def test_accepts_invoice_data_models_and_dicts(self, mock_pw):
        page = mock.MagicMock()
        new_page_info = SimpleNamespace(value=page)
        context = mock.MagicMock()
        context.new_page.return_value = page
        context.expect_page.return_value.__enter__.return_value = new_page_info
        browser = mock.MagicMock()
        browser.new_context.return_value = context
        session = mock.MagicMock()
        session.chromium.launch.return_value = browser
        mock_pw.return_value.__enter__.return_value = session

        invoice_model = InvoiceData(
            vendor_cuit="30117368544",
            point_of_sale=4,
            receipt_number=12891,
            issue_date="2026-03-15",
            total_amount=20000.00,
            receipt_type="FACTURA_B",
            suggested_category=SiRADIGCategory.GASTOS_EDUCACION,
        )
        res = self._make_automator().run_draft_upload(fiscal_year=2026, deductions=[invoice_model])

        self.assertTrue(res.success)
        self.assertEqual(res.saved_count, 1)
        self.assertEqual(res.items[0].invoice_id, "30117368544-0004-00012891")


if __name__ == "__main__":
    unittest.main()
