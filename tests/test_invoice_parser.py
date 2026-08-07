"""
Unit tests for invoice parsing regex and category heuristics.
"""

import unittest
from src.parser.invoice_parser import parse_invoice_text, detect_suggested_category
from src.models.invoice import ReceiptType, SiRADIGCategory


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
        self.assertEqual(detect_suggested_category("Honorarios Medico Consulta Odontologia"), SiRADIGCategory.MEDICO_PARAMEDICO)
        self.assertEqual(detect_suggested_category("Pago Plan Mensual OSDE Medicina Prepaga"), SiRADIGCategory.CUOTA_MEDICO_ASSIST)
        self.assertEqual(detect_suggested_category("Alquiler departamento habitacion contrato"), SiRADIGCategory.ALQUILER_HABITACION)
        self.assertEqual(detect_suggested_category("Personal Casas Particulares VEP Afip"), SiRADIGCategory.CASAS_PARTICULARES)


if __name__ == "__main__":
    unittest.main()
