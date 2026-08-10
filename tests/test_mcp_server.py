"""
Unit tests for MCP server tool dispatching.
"""

import unittest

from src.mcp.server import handle_json_rpc


class TestMCPServer(unittest.TestCase):
    def test_mcp_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        res = handle_json_rpc(req)
        self.assertEqual(res["id"], 1)
        self.assertIn("tools", res["result"])
        self.assertEqual(len(res["result"]["tools"]), 4)

    def test_mcp_compute_deductions_engine_tool(self):
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "compute_deductions_engine",
            "params": {
                "invoice_data": {"total_amount": 50000.00, "reimbursed_amount": 0.0, "fiscal_year": 2026},
                "siradig_code": "GASTOS_EDUCACION",
            },
        }
        res = handle_json_rpc(req)
        self.assertEqual(res["id"], 2)
        self.assertEqual(res["result"]["computable_deduction"], 50000.00)


if __name__ == "__main__":
    unittest.main()
