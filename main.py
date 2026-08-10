"""
ARCA / AFIP SiRADIG F.572 Web - Command Line Interface (CLI) Orchestrator.
Coordinates the end-to-end tax deduction pipeline:
1. F.572 PDF Sync (vistaprevia/) -> .env auto-populate
2. Invoice PDFs Ingestion (invoices/) -> JSON extraction & OCR fallback
3. Duplicate verification against loaded F.572
4. Legal Validation (Modulo 11, CAE, dates, dependents)
5. RG 4003/17 Annual Caps Engine (MNI & GNA limits)
6. Playwright Browser Draft Upload (Guardar Borrador)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config.settings import settings
from src.browser.siradig_automator import SiRADIGAutomator
from src.engine.deduction_calculator import compute_batch_deductions
from src.parser.f572_parser import is_invoice_already_in_f572, process_vistaprevia_f572
from src.parser.invoice_parser import process_pdf_invoice
from src.utils.logger import logger, setup_logging
from src.validator.legal_validator import validate_invoice_detailed


def cmd_sync_f572(args) -> int:
    """Syncs existing F.572 export PDF from vistaprevia/ into .env."""
    folder = Path(args.vistaprevia_dir)
    pdf_files = list(folder.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No F.572 PDF files found in {folder}/.")
        return 1

    for pdf_file in pdf_files:
        logger.info(f"Processing F.572 Vista Previa: {pdf_file.name}")
        f572_data = process_vistaprevia_f572(str(pdf_file), sync_env=True)
        print(f"\n[OK] Synced Taxpayer: {f572_data.taxpayer_name} (CUIT: {f572_data.taxpayer_cuit})")
        print(f"[OK] Fiscal Year: {f572_data.fiscal_year}")
        print(f"[OK] Registered Dependents: {len(f572_data.dependents)}")
        print(f"[OK] Loaded Invoices in F.572: {len(f572_data.loaded_invoices)}")

    return 0


def cmd_parse_invoices(args) -> int:
    """Parses all candidate invoice PDFs from invoices/ directory."""
    folder = Path(args.invoices_dir)
    pdf_files = list(folder.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No invoice PDF files found in {folder}/.")
        return 1

    print(f"\nFound {len(pdf_files)} invoice PDFs in {folder}/...")
    for pdf_file in pdf_files:
        res = process_pdf_invoice(str(pdf_file))
        if res.success and res.invoice:
            print(
                f"[EXTRACTED] {pdf_file.name} -> {res.invoice.receipt_type.value} "
                f"| Total: ${res.invoice.total_amount:,.2f} | CUIT: {res.invoice.vendor_cuit}"
            )
        else:
            print(f"[FAILED/WARNING] {pdf_file.name} -> Errors: {res.errors}")
    return 0


def collect_validated_invoices(args, verbose: bool = True) -> list[dict]:
    """Loads candidate invoice JSONs from invoices/, filters out duplicates already loaded
    in the F.572 export and invoices failing legal validation.

    Prints the validation / duplicate report (unless ``verbose=False``) and returns the eligible subset.
    """
    # 1. Load F.572 export if available
    vp_dir = Path(args.vistaprevia_dir)
    f572_jsons = list(vp_dir.glob("*.json"))
    f572_data = None
    if f572_jsons:
        with open(f572_jsons[0], encoding="utf-8") as f:
            f572_data = json.load(f)

    # 2. Load candidate invoices
    inv_dir = Path(args.invoices_dir)
    inv_jsons = list(inv_dir.glob("*.json"))
    if not inv_jsons:
        logger.info("No extracted invoice JSONs found. Running extraction first...")
        cmd_parse_invoices(args)
        inv_jsons = list(inv_dir.glob("*.json"))

    fiscal_year = args.fiscal_year or settings.fiscal_year
    dependents = [d.to_dict() for d in settings.dependents]

    valid_invoices = []
    if verbose:
        print("\n" + "=" * 80)
        print(f"TAX VALIDATION & DUPLICATE REPORT - FISCAL YEAR {fiscal_year}")
        print("=" * 80)

    for inv_json_path in inv_jsons:
        with open(inv_json_path, encoding="utf-8") as f:
            inv_dict = json.load(f)

        # Check duplicate
        if f572_data and is_invoice_already_in_f572(inv_dict, f572_data):
            if verbose:
                print(f"[DUPLICATE / SKIP] {inv_json_path.name} is already registered in F.572 export.")
            continue

        # Check legal requirements
        val_res = validate_invoice_detailed(inv_dict, dependents, fiscal_year)
        if not val_res.is_valid:
            if verbose:
                print(f"[LEGAL ERROR] {inv_json_path.name} failed validation: {val_res.errors}")
            continue

        valid_invoices.append(inv_dict)
        if verbose:
            print(
                f"[VALID] {inv_json_path.name} | CUIT: {inv_dict.get('vendor_cuit')} "
                f"| Amount: ${inv_dict.get('total_amount', 0):,.2f}"
            )

    return valid_invoices


def cmd_validate_and_compute(args) -> int:
    """Validates candidate invoices, checks duplicates against F.572, and computes annual caps."""
    valid_invoices = collect_validated_invoices(args)
    if not valid_invoices:
        print("\nNo eligible new invoices to compute.")
        return 0

    # Compute Deductions & Annual Caps
    fiscal_year = args.fiscal_year or settings.fiscal_year
    summary = compute_batch_deductions(valid_invoices, fiscal_year=fiscal_year)
    print("\n" + "=" * 80)
    print("RG 4003/17 DEDUCTION ENGINE SUMMARY")
    print("=" * 80)
    print(f"Total Eligible Invoices: {summary.total_invoices_evaluated}")
    print(f"Total Gross Amount:      ${summary.total_gross_amount:,.2f}")
    print(f"Total Net Out-of-Pocket: ${summary.total_net_out_of_pocket:,.2f}")
    print(f"Total Computable Deduction: ${summary.total_computable_deductions:,.2f}")

    if summary.warnings:
        print("\nWarnings / Cap Alerts:")
        for w in summary.warnings:
            print(f"  * {w}")

    # Output JSON summary if requested
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as out_f:
            json.dump(summary.model_dump(), out_f, indent=2, ensure_ascii=False)
        print(f"\nSaved calculation summary to {args.output_json}")

    return 0


def cmd_upload_draft(args) -> int:
    """Uploads validated, non-duplicate deductions to SiRADIG in DRAFT mode only.

    Single-step command: reuses previously extracted invoice JSONs and the F.572
    export (if present) to select the eligible subset, then launches the browser.
    """
    print("\n>>> Launching SiRADIG Playwright Automator (DRAFT MODE ONLY)...")
    # Reuse the validated, non-duplicate subset ONLY — never upload raw/unfiltered JSONs.
    valid_invoices = collect_validated_invoices(args)
    if not valid_invoices:
        print("\n[WARNING] No validated invoices to upload. Skipping browser upload.")
        return 0

    automator = SiRADIGAutomator(
        cuil=settings.arca_cuil,
        clave_fiscal=settings.arca_clave_fiscal,
        headless=args.headless,
        slow_mo=settings.browser_slowmo_ms,
    )
    res = automator.run_draft_upload(fiscal_year=args.fiscal_year or settings.fiscal_year, deductions=valid_invoices)
    print(f"\n[UPLOAD RESULT] Success: {res.success} | Saved Items: {res.saved_count}/{res.processed_count}")
    if res.error:
        print(f"[ERROR] {res.error}")
    return 0


def cmd_pipeline(args) -> int:
    """Executes the complete end-to-end pipeline."""
    print("\n>>> STEP 1: Syncing F.572 Vista Previa export...")
    cmd_sync_f572(args)

    print("\n>>> STEP 2: Extracting candidate invoices...")
    cmd_parse_invoices(args)

    print("\n>>> STEP 3: Running Legal Validation & Cap Calculations...")
    cmd_validate_and_compute(args)

    if args.upload_draft:
        print("\n>>> STEP 4: Uploading validated deductions as drafts...")
        return cmd_upload_draft(args)

    return 0


def main():
    parser = argparse.ArgumentParser(description="ARCA / AFIP SiRADIG F.572 Web CLI Orchestrator")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # Global options
    parser.add_argument("--vistaprevia-dir", default="vistaprevia", help="Directory containing F.572 PDFs")
    parser.add_argument("--invoices-dir", default="invoices", help="Directory containing candidate invoice PDFs")
    parser.add_argument("--fiscal-year", type=int, default=2026, help="Target fiscal year (default: 2026)")
    parser.add_argument("--log-level", default="INFO", help="Logging level: DEBUG, INFO, WARNING, ERROR")

    # sync-f572
    subparsers.add_parser("sync-f572", help="Sync F.572 Vista Previa export to .env")

    # parse-invoices
    subparsers.add_parser("parse-invoices", help="Parse PDF invoices in invoices/ directory")

    # validate
    val_p = subparsers.add_parser("validate", help="Validate invoices and compute RG 4003/17 annual caps")
    val_p.add_argument("--output-json", help="Optional path to write calculation summary JSON")

    # upload-draft
    upload_p = subparsers.add_parser(
        "upload-draft", help="Upload validated, non-duplicate deductions to SiRADIG in DRAFT mode (single step)"
    )
    upload_p.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    # pipeline
    pipe_p = subparsers.add_parser("pipeline", help="Run full end-to-end pipeline")
    pipe_p.add_argument("--upload-draft", action="store_true", help="Include Playwright draft upload step")
    pipe_p.add_argument("--headless", action="store_true", help="Run browser headless during upload")
    pipe_p.add_argument("--output-json", help="Optional path to write calculation summary JSON")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if not args.command or args.command == "pipeline":
        return cmd_pipeline(args)
    elif args.command == "sync-f572":
        return cmd_sync_f572(args)
    elif args.command == "parse-invoices":
        return cmd_parse_invoices(args)
    elif args.command == "validate":
        return cmd_validate_and_compute(args)
    elif args.command == "upload-draft":
        return cmd_upload_draft(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
