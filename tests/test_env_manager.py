"""
Unit tests for the safe .env manager (safe_update_env).
"""

import os
import tempfile
import unittest

from src.utils.env_manager import safe_update_env


class TestEnvManager(unittest.TestCase):
    def test_creates_new_env_file_with_header(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = os.path.join(tmp_dir, ".env")
            success = safe_update_env({"ARCA_CUIL": "20123456789"}, env_file_path=env_path)
            self.assertTrue(success)

            with open(env_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("# ARCA / AFIP SiRADIG F.572 Environment Configuration", content)
            self.assertIn("ARCA_CUIL=20123456789", content)

    def test_updates_existing_key_in_place(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = os.path.join(tmp_dir, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("ARCA_CUIL=old_value\n")
                f.write("UNRELATED_VAR=keep_me\n")

            success = safe_update_env({"ARCA_CUIL": "20780009188"}, env_file_path=env_path)
            self.assertTrue(success)

            with open(env_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("ARCA_CUIL=20780009188", content)
            self.assertIn("UNRELATED_VAR=keep_me", content)
            self.assertNotIn("old_value", content)

    def test_multiple_keys_and_none_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = os.path.join(tmp_dir, ".env")
            success = safe_update_env(
                {"FISCAL_YEAR": "2026", "TAXPAYER_NAME": "Juan Perez", "EMPTY_VAR": None}, env_file_path=env_path
            )
            self.assertTrue(success)

            with open(env_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("FISCAL_YEAR=2026", content)
            self.assertIn("TAXPAYER_NAME=Juan Perez", content)
            self.assertIn("EMPTY_VAR=", content)

    def test_returns_false_on_invalid_path(self):
        # A path inside a non-existent directory should fail gracefully.
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = os.path.join(tmp_dir, "no_such_dir", ".env")
            self.assertFalse(safe_update_env({"ARCA_CUIL": "20123456789"}, env_file_path=bad_path))


if __name__ == "__main__":
    unittest.main()
