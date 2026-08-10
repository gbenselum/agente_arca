"""
Unit tests for invoice parsing regex and category heuristics.
"""

import os
import tempfile
import unittest
from unittest import mock

from src.models.invoice import ReceiptType, SiRADIGCategory
from src.parser.invoice_parser import (
    OCR_AVAILABLE,
    _rasterize_pdf_pages,
    detect_suggested_category,
    extract_text_via_ocr_fallback,
    parse_invoice_text,
)


class TestInvoiceParser(unittest.TestCase):
    def test_parse_afip_factura_b_text(self):
        sample_text = """
        ORIGINAL
        COLEGIO SAN MARTIN DE TOURS
        Razón Social: ASOCIACION EDUCATIVA ARGENTINA
        CUIT: 30-71123456-6
        FACTURA B
        Punto de Venta: 0004 Comp. Nro: 00012890
        Fecha de Emisión: 15/03/2026
        Concepto: Cuota escolar Marzo 2026 y Materiales
        CUIT del Comprador: 20-12345678-9
        TOTAL: $ 145.250,50
        CAE: 74123456789012
        Fecha de Vto. de CAE: 25/03/2026
        """
        inv = parse_invoice_text(sample_text)
        self.assertEqual(inv.vendor_cuit, "30711234566")
        self.assertEqual(inv.receipt_type, ReceiptType.FACTURA_B)
        self.assertEqual(inv.point_of_sale, 4)
        self.assertEqual(inv.receipt_number, 12890)
        self.assertEqual(inv.issue_date, "2026-03-15")
        self.assertEqual(inv.total_amount, 145250.50)
        self.assertEqual(inv.cae, "74123456789012")
        self.assertEqual(inv.cae_due_date, "2026-03-25")
        self.assertEqual(inv.suggested_category, SiRADIGCategory.GASTOS_EDUCACION)

    def test_category_detection_keywords(self):
        self.assertEqual(
            detect_suggested_category("Honorarios Medico Consulta Odontologia"), SiRADIGCategory.MEDICO_PARAMEDICO
        )
        self.assertEqual(
            detect_suggested_category("Pago Plan Mensual OSDE Medicina Prepaga"), SiRADIGCategory.CUOTA_MEDICO_ASSIST
        )
        self.assertEqual(
            detect_suggested_category("Alquiler departamento habitacion contrato"), SiRADIGCategory.ALQUILER_HABITACION
        )
        self.assertEqual(
            detect_suggested_category("Personal Casas Particulares VEP Afip"), SiRADIGCategory.CASAS_PARTICULARES
        )

    def test_category_detection_unknown_fallback(self):
        # Unrecognized text must map to UNKNOWN, NOT silently default to education.
        self.assertEqual(detect_suggested_category("Compra de articulos de ferreteria"), SiRADIGCategory.UNKNOWN)
        self.assertEqual(detect_suggested_category(""), SiRADIGCategory.UNKNOWN)
        self.assertEqual(detect_suggested_category("1234567890 sin contenido util"), SiRADIGCategory.UNKNOWN)


class TestOcrFallback(unittest.TestCase):
    """OCR fallback must rasterize PDFs to images before calling Tesseract."""

    def _make_pdf_with_text(self, path: str) -> None:
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "FACTURA B", fontsize=20)
        page.insert_text((72, 120), "CUIT: 30-71123456-6", fontsize=12)
        doc.save(path)
        doc.close()

    @unittest.skipUnless(OCR_AVAILABLE, "pytesseract/Pillow not installed")
    def test_pdf_is_rasterized_before_ocr(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, "scan.pdf")
            self._make_pdf_with_text(pdf_path)

            # Tesseract receives PIL images, never the raw PDF path.
            received = []

            def fake_image_to_string(img, **kwargs):
                received.append(img)
                return "FACTURA B"

            with mock.patch("src.parser.invoice_parser.pytesseract.image_to_string", side_effect=fake_image_to_string):
                out = extract_text_via_ocr_fallback(pdf_path)

            self.assertEqual(out, "FACTURA B")
            self.assertEqual(len(received), 1)
            self.assertTrue(hasattr(received[0], "load"), "expected a PIL image, got non-image input")

    @unittest.skipUnless(OCR_AVAILABLE, "pytesseract/Pillow not installed")
    def test_rasterize_pdf_pages_returns_images(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, "pages.pdf")
            import pymupdf

            doc = pymupdf.open()
            doc.new_page()
            doc.new_page()
            doc.save(pdf_path)
            doc.close()

            images = _rasterize_pdf_pages(pdf_path)
            self.assertEqual(len(images), 2)
            self.assertEqual(images[0].mode, "RGB")

    @unittest.skipUnless(OCR_AVAILABLE, "pytesseract/Pillow not installed")
    def test_unsupported_file_type_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc_path = os.path.join(tmp_dir, "not_an_image.doc")
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write("plain text")
            out = extract_text_via_ocr_fallback(doc_path)
            self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
