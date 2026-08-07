"""
MCP (Model Context Protocol) Server for ARCA SiRADIG F.572 Agent.
Exposes standard JSON-RPC tools for LLM agent integration.
"""

import sys
import json
import os
from typing import Dict, Any, List, Optional

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.parser.invoice_parser import parse_invoice_text, process_pdf_invoice
from src.validator.legal_validator import validate_invoice_detailed
from src.engine.deduction_calculator import compute_deduction, generate_siradig_payload
from src.models.invoice import InvoiceData
from src.utils.logger import logger


def tool_parse_and_extract_invoice(raw_text: Optional[str] = None, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Extracts structured tax details from OCR text or document images."""
    if file_path:
        res = process_pdf_invoice(file_path)
        return {
            "success": res.success,
            "invoice_data": res.invoice.model_dump() if res.invoice else None,
            "warnings": res.warnings,
            "errors": res.errors
        }
    elif raw_text:
        inv = parse_invoice_text(raw_text)
        return {
            "success": True,
            "invoice_data": inv.model_dump()
        }
    else:
        return {"success": False, "error": "Must provide either raw_text or file_path."}


def tool_validate_deduction_eligibility(invoice_data: Dict[str, Any], taxpayer_data: Dict[str, Any]) -> Dict[str, Any]:
    """Verifies tax parameters before computing deductible amounts."""
    fiscal_year = int(taxpayer_data.get("fiscal_year", 2026))
    dependents = taxpayer_data.get("dependents", [])
    val_res = validate_invoice_detailed(invoice_data, dependents, fiscal_year)
    return val_res.model_dump()


def tool_compute_deductions_engine(invoice_data: Dict[str, Any], siradig_code: str) -> Dict[str, Any]:
    """Calculates net deductible amount and applies category specific formulas."""
    fiscal_year = int(invoice_data.get("fiscal_year", 2026))
    res = compute_deduction(invoice_data, siradig_code, fiscal_year=fiscal_year)
    return res


def tool_generate_siradig_payload(taxpayer_cuit: str, fiscal_year: int, deductions_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compiles all validated deductions for the specified fiscal year into standard JSON format."""
    return generate_siradig_payload(taxpayer_cuit, fiscal_year, deductions_list)


# Dispatch map
TOOLS = {
    "parse_and_extract_invoice": tool_parse_and_extract_invoice,
    "validate_deduction_eligibility": tool_validate_deduction_eligibility,
    "compute_deductions_engine": tool_compute_deductions_engine,
    "generate_siradig_payload": tool_generate_siradig_payload
}


def handle_json_rpc(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handles JSON-RPC request for MCP tools."""
    req_id = request.get("id", 1)
    method = request.get("method")
    params = request.get("params", {})

    if method == "tools/list":
        with open("mcp_tools_schema.json", "r", encoding="utf-8") as f:
            schema = json.load(f)
        return {"jsonrpc": "2.0", "id": req_id, "result": schema}

    elif method in TOOLS:
        try:
            result = TOOLS[method](**params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method {method} not found"}}


def run_stdio_server():
    """Runs standard stdio JSON-RPC loop."""
    logger.info("Starting ARCA SiRADIG MCP stdio server...")
    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            req = json.loads(line_str)
            res = handle_json_rpc(req)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_res = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
