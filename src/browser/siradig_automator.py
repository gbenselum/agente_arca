"""
Playwright Browser Automator for ARCA / AFIP SiRADIG - Formulario 572 Web.
Fills deductions across categories, captures verification screenshots, and saves
them strictly as DRAFT (Guardar Borrador).
"""

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..models.automator import AutomatorBatchResult, AutomatorItemResult
from ..models.invoice import InvoiceData, SiRADIGCategory
from ..utils.logger import logger

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore[assignment]


class SiRADIGAutomator:
    def __init__(
        self,
        cuil: str,
        clave_fiscal: str,
        headless: bool = False,
        slow_mo: int = 500,
        screenshots_dir: str = "screenshots",
    ):
        self.cuil = cuil.replace("-", "")
        self.clave_fiscal = clave_fiscal
        self.headless = headless
        self.slow_mo = slow_mo
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def _take_screenshot(self, page: Any, step_name: str) -> str:
        """Captures verification screenshot with timestamp."""
        try:
            timestamp = int(time.time())
            filename = f"siradig_{step_name}_{timestamp}.png"
            path = self.screenshots_dir / filename
            page.screenshot(path=str(path), full_page=True)
            logger.info(f"Captured screenshot: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Could not take screenshot for {step_name}: {e}")
            return ""

    def _fill_medical_expense(self, page: Any, item: dict[str, Any]) -> None:
        """Navigates and fills Gastos Médicos y Paramédicos."""
        logger.info(f"Filling Medical expense: {item.get('vendor_cuit')}")
        # Click category menu entry
        page.click("text=Médicos y Paramédicos", timeout=5000)
        page.click("input[value='Alta de Comprobante']", timeout=5000)

        # Fill CUIT of medical professional / clinic
        page.fill("input#cuitPrestador", str(item.get("vendor_cuit", "")))
        page.click("input#btnBuscarPrestador")
        page.wait_for_load_state("networkidle")

        # Comprobante details
        page.select_option("select#tipoComprobante", item.get("receipt_type", "FACTURA_B"))
        if item.get("point_of_sale"):
            page.fill("input#puntoVenta", str(item["point_of_sale"]))
        if item.get("receipt_number"):
            page.fill("input#nroComprobante", str(item["receipt_number"]))

        # Dates & Amounts
        if item.get("issue_date"):
            page.fill("input#fechaEmision", item["issue_date"])
        page.fill("input#montoTotal", f"{float(item.get('total_amount', 0.0)):.2f}")
        if item.get("reimbursed_amount"):
            page.fill("input#montoReintegro", f"{float(item['reimbursed_amount']):.2f}")

        # Beneficiary
        if item.get("beneficiary_cuil"):
            page.select_option("select#cuitBeneficiario", item["beneficiary_cuil"])

    def _fill_education_expense(self, page: Any, item: dict[str, Any]) -> None:
        """Navigates and fills Gastos de Educación."""
        logger.info(f"Filling Education expense: {item.get('vendor_cuit')}")
        page.click("text=Gastos de Educación", timeout=5000)
        page.click("input[value='Alta de Comprobante']", timeout=5000)

        # Fill CUIT of institution
        page.fill("input#cuitInstitucion", str(item.get("vendor_cuit", "")))
        page.click("input#btnBuscarInstitucion")
        page.wait_for_load_state("networkidle")

        # Type of expense (Cuota / Materiales escolares)
        page.select_option("select#tipoGastoEducacion", "1")  # 1: Servicios de enseñanza / 2: Herramientas

        # Comprobante details
        page.select_option("select#tipoComprobante", item.get("receipt_type", "FACTURA_B"))
        if item.get("point_of_sale"):
            page.fill("input#puntoVenta", str(item["point_of_sale"]))
        if item.get("receipt_number"):
            page.fill("input#nroComprobante", str(item["receipt_number"]))

        if item.get("issue_date"):
            page.fill("input#fechaEmision", item["issue_date"])
        page.fill("input#montoTotal", f"{float(item.get('total_amount', 0.0)):.2f}")

        # Linked dependent (Hijo/a hasta 24 años)
        if item.get("beneficiary_cuil"):
            page.select_option("select#cuitFamiliar", item["beneficiary_cuil"])

    def _fill_rental_expense(self, page: Any, item: dict[str, Any]) -> None:
        """Navigates and fills Alquiler de Casa Habitación."""
        logger.info(f"Filling Rental expense: {item.get('vendor_cuit')}")
        page.click("text=Alquiler de inmuebles destinados a casa habitación", timeout=5000)
        page.click("input[value='Alta de Comprobante']", timeout=5000)

        page.fill("input#cuitLocador", str(item.get("vendor_cuit", "")))
        if item.get("point_of_sale"):
            page.fill("input#puntoVenta", str(item["point_of_sale"]))
        if item.get("receipt_number"):
            page.fill("input#nroComprobante", str(item["receipt_number"]))
        if item.get("issue_date"):
            page.fill("input#fechaEmision", item["issue_date"])
        page.fill("input#montoTotal", f"{float(item.get('total_amount', 0.0)):.2f}")

    def _fill_domestic_service(self, page: Any, item: dict[str, Any]) -> None:
        """Navigates and fills Casas Particulares / Servicio Doméstico."""
        logger.info(f"Filling Domestic Service expense: {item.get('vendor_cuit')}")
        page.click("text=Personal de Casas Particulares", timeout=5000)
        page.click("input[value='Alta de Comprobante']", timeout=5000)

        page.fill("input#cuitTrabajador", str(item.get("vendor_cuit", "")))
        page.fill("input#montoAportes", f"{float(item.get('total_amount', 0.0)):.2f}")

    def run_draft_upload(
        self, fiscal_year: int, deductions: Sequence[InvoiceData | dict[str, Any]]
    ) -> AutomatorBatchResult:
        """
        Launches browser, logs in to ARCA portal, opens SiRADIG Trabajador,
        loads each deduction category, and strictly saves as draft (Guardar Borrador).
        """
        start_time = time.time()
        if sync_playwright is None:
            return AutomatorBatchResult(
                success=False,
                fiscal_year=fiscal_year,
                error=(
                    "Playwright is not installed. Please run `pip install playwright && playwright install chromium`."
                ),
            )

        if not self.cuil or not self.clave_fiscal:
            return AutomatorBatchResult(
                success=False,
                fiscal_year=fiscal_year,
                error="Missing CUIL or Clave Fiscal credentials in environment (.env).",
            )

        processed_items: list[AutomatorItemResult] = []
        session_screenshots: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
            context = browser.new_context(viewport={"width": 1366, "height": 868})
            page = context.new_page()

            try:
                logger.info(f"Logging in to ARCA for CUIT {self.cuil} (Fiscal Year: {fiscal_year})...")
                # Step 1: Login to ARCA / AFIP Portal
                page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml", wait_until="networkidle")

                # Fill CUIL
                page.fill("input#F1\\:username", self.cuil)
                page.click("input#F1\\:btnSiguiente")
                page.wait_for_selector("input#F1\\:password", timeout=12000)

                # Fill Clave Fiscal
                page.fill("input#F1\\:password", self.clave_fiscal)
                page.click("input#F1\\:btnIngresar")
                page.wait_for_load_state("networkidle")

                session_screenshots.append(self._take_screenshot(page, "01_login_success"))

                # Step 2: Search and Open 'SiRADIG - Trabajador'
                with context.expect_page() as new_page_info:
                    page.click("text=SiRADIG - Trabajador")
                siradig_page = new_page_info.value
                siradig_page.wait_for_load_state("networkidle")
                session_screenshots.append(self._take_screenshot(siradig_page, "02_siradig_home"))

                # Step 3: Select Taxpayer profile & Fiscal Year
                siradig_page.select_option("select#periodo", str(fiscal_year))
                siradig_page.click("input[value='Continuar']")
                siradig_page.wait_for_load_state("networkidle")

                # Step 4: Navigate to "Carga de Formulario" -> "Deducciones y desgravaciones"
                siradig_page.click("text=Carga de Formulario")
                siradig_page.click("text=Deducciones y desgravaciones")
                siradig_page.wait_for_load_state("networkidle")

                # Step 5: Process each deduction entry
                for item in deductions:
                    item_dict = item.model_dump() if isinstance(item, InvoiceData) else dict(item)
                    category = item_dict.get("suggested_category") or item_dict.get("siradig_code")
                    if category is None:
                        category = SiRADIGCategory.UNKNOWN.value
                    if isinstance(category, SiRADIGCategory):
                        category = category.value

                    cuit = item_dict.get("vendor_cuit", "")
                    pos = item_dict.get("point_of_sale")
                    num = item_dict.get("receipt_number")
                    inv_id = f"{cuit}-{pos or 0:04d}-{num or 0:08d}"

                    # UNKNOWN is not a real SiRADIG code: reject rather than silently file as education.
                    if category == SiRADIGCategory.UNKNOWN.value:
                        skip_msg = f"Skipping {inv_id}: suggested category is UNKNOWN (requires manual categorization)."
                        logger.warning(skip_msg)
                        processed_items.append(
                            AutomatorItemResult(
                                siradig_code=category,
                                invoice_id=inv_id,
                                status="FAILED",
                                category_name=category,
                                point_of_sale=pos,
                                receipt_number=num,
                                amount=float(item_dict.get("total_amount", 0.0)),
                                error=(
                                    "Category is UNKNOWN (not auto-detectable). "
                                    "Set suggested_category manually before uploading."
                                ),
                            )
                        )
                        continue

                    logger.info(f"Processing deduction {inv_id} for category {category}")

                    try:
                        if category in ("MEDICO_PARAMEDICO", "CUOTA_MEDICO_ASSIST"):
                            self._fill_medical_expense(siradig_page, item_dict)
                        elif category == "GASTOS_EDUCACION":
                            self._fill_education_expense(siradig_page, item_dict)
                        elif category in ("ALQUILER_HABITACION", "ALQUILER_ADICIONAL_10"):
                            self._fill_rental_expense(siradig_page, item_dict)
                        elif category == "CASAS_PARTICULARES":
                            self._fill_domestic_service(siradig_page, item_dict)
                        else:
                            self._fill_education_expense(siradig_page, item_dict)

                        # STRICT GUARDRAIL: Click ONLY "Guardar" / Borrador
                        siradig_page.click("input[value='Guardar']", timeout=6000)
                        siradig_page.wait_for_load_state("networkidle")

                        shot = self._take_screenshot(siradig_page, f"draft_saved_{inv_id}")
                        session_screenshots.append(shot)

                        processed_items.append(
                            AutomatorItemResult(
                                siradig_code=category,
                                invoice_id=inv_id,
                                status="DRAFT_SAVED",
                                category_name=category,
                                point_of_sale=pos,
                                receipt_number=num,
                                amount=float(item_dict.get("total_amount", 0.0)),
                                screenshot_path=shot,
                            )
                        )

                        # Return to Deductions menu for next item
                        siradig_page.click("text=Deducciones y desgravaciones", timeout=5000)
                        siradig_page.wait_for_load_state("networkidle")

                    except Exception as item_error:
                        logger.error(f"Error loading item {inv_id}: {item_error}")
                        err_shot = self._take_screenshot(siradig_page, f"error_{inv_id}")
                        processed_items.append(
                            AutomatorItemResult(
                                siradig_code=category,
                                invoice_id=inv_id,
                                status="FAILED",
                                category_name=category,
                                point_of_sale=pos,
                                receipt_number=num,
                                amount=float(item_dict.get("total_amount", 0.0)),
                                screenshot_path=err_shot,
                                error=str(item_error),
                            )
                        )

                elapsed = time.time() - start_time
                saved_count = sum(1 for i in processed_items if i.status == "DRAFT_SAVED")
                failed_count = sum(1 for i in processed_items if i.status == "FAILED")

                return AutomatorBatchResult(
                    success=failed_count == 0 and len(processed_items) > 0,
                    fiscal_year=fiscal_year,
                    processed_count=len(processed_items),
                    saved_count=saved_count,
                    failed_count=failed_count,
                    items=processed_items,
                    message=f"Successfully loaded {saved_count} items in DRAFT state into SiRADIG Trabajador F.572.",
                    session_screenshots=session_screenshots,
                    execution_time_seconds=round(elapsed, 2),
                )

            except Exception as e:
                logger.error(f"Automation encountered a fatal error: {e}")
                fail_shot = self._take_screenshot(page, "fatal_error")
                return AutomatorBatchResult(
                    success=False,
                    fiscal_year=fiscal_year,
                    error=str(e),
                    message="Automation encountered an error. Please verify portal status or credentials in .env.",
                    session_screenshots=[fail_shot] if fail_shot else [],
                )
            finally:
                if not self.headless:
                    time.sleep(3)
                browser.close()
