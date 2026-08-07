"""
Safe .env environment file manager.
Updates only specific keys using python-dotenv's set_key without destroying existing comments or variables.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import set_key, load_dotenv
from .logger import logger


def safe_update_env(updates: Dict[str, Any], env_file_path: str = ".env") -> bool:
    """
    Safely updates or appends key-value pairs in the specified .env file.
    Preserves all existing comments, whitespace, and unrelated environment variables.
    """
    env_path = Path(env_file_path).resolve()

    # If .env does not exist, create it with a header comment
    if not env_path.exists():
        logger.info(f"Creating new .env file at {env_path}")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# ARCA / AFIP SiRADIG F.572 Environment Configuration\n")

    try:
        for key, value in updates.items():
            str_val = "" if value is None else str(value)
            set_key(dotenv_path=str(env_path), key_to_set=key, value_to_set=str_val, quote_mode="never")
            logger.debug(f"Updated .env key: {key}")

        # Reload dotenv into process environment
        load_dotenv(dotenv_path=str(env_path), override=True)
        logger.info(f"Successfully synced {len(updates)} variables to {env_path.name} without altering other entries.")
        return True
    except Exception as e:
        logger.error(f"Failed to safely update .env file {env_path}: {e}")
        return False
