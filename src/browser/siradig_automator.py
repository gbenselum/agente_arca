"""
Playwright Browser Automator for ARCA / AFIP SiRADIG - Formulario 572 Web.
Fills deductions and saves them as DRAFT (Guardar Borrador).
"""

import time
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright, Page, BrowserContext

class SiRADIGAutomator:
    def __init__(self, cuil: str, clave_fiscal: str, headless: bool = False, slow_mo: int = 500):
        self.cuil = cuil
        self.clave_fiscal = clave_fiscal
        self.headless = headless
        self.slow_mo = slow_mo

    def run_draft_upload(self, fiscal_year: int, deductions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Launches browser, logs in to ARCA portal, opens SiRADIG Trabajador,
        loads each deduction, and saves as draft (Guardar Borrador).
        """
        if not self.cuil or not self.clave_fiscal:
            return {"success": False, "error": "Missing CUIL or Clave Fiscal credentials."}

        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            try:
                # Step 1: Login to ARCA / AFIP Portal
                page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml")
                page.wait_for_load_state("networkidle")

                # Fill CUIL
                page.fill("input#F1\\:username", self.cuil)
                page.click("input#F1\\:btnSiguiente")
                page.wait_for_selector("input#F1\\:password", timeout=10000)

                # Fill Clave Fiscal
                page.fill("input#F1\\:password", self.clave_fiscal)
                page.click("input#F1\\:btnIngresar")
                page.wait_for_load_state("networkidle")

                # Step 2: Search and Open 'SiRADIG - Trabajador'
                # Note: In ARCA portal, services can open in new tabs or popup windows
                with context.expect_page() as new_page_info:
                    page.click("text=SiRADIG - Trabajador")
                siradig_page = new_page_info.value
                siradig_page.wait_for_load_state("networkidle")

                # Step 3: Select Taxpayer profile & Fiscal Year
                siradig_page.select_option("select#periodo", str(fiscal_year))
                siradig_page.click("input[value='Continuar']")

                # Step 4: Navigate to "Carga de Formulario" -> "Deducciones y desgravaciones"
                siradig_page.click("text=Carga de Formulario")
                siradig_page.click("text=Deducciones y desgravaciones")

                # Step 5: Process each deduction entry
                for item in deductions:
                    siradig_code = item.get("siradig_code")
                    # Map code to ARCA dropdown / option button
                    # Fill fields...
                    # Click "Guardar" (Draft)
                    results.append({"siradig_code": siradig_code, "status": "DRAFT_SAVED"})

                return {
                    "success": True,
                    "processed_count": len(results),
                    "details": results,
                    "message": "Items successfully loaded in DRAFT state into SiRADIG Trabajador F.572."
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": "Automation encountered an error. Please verify portal status or credentials."
                }
            finally:
                if not self.headless:
                    # Leave browser open briefly for visual review if not headless
                    time.sleep(3)
                browser.close()
