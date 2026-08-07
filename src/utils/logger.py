"""
Structured logging module for ARCA agent with secret masking and formatted outputs.
"""

import logging
import os
import sys
from typing import Optional


def mask_secret(value: str, visible_chars: int = 2) -> str:
    """Masks sensitive credentials showing only the first and last few characters."""
    if not value:
        return ""
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return f"{value[:visible_chars]}{'*' * (len(value) - visible_chars * 2)}{value[-visible_chars:]}"


class SensitiveFilter(logging.Filter):
    """Filter that masks known sensitive patterns (Clave Fiscal, secrets) in log records."""
    def __init__(self, secrets_to_mask: Optional[list[str]] = None):
        super().__init__()
        self.secrets = secrets_to_mask or []

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for secret in self.secrets:
                if secret and len(secret) > 3:
                    record.msg = record.msg.replace(secret, mask_secret(secret))
        return True


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Configures structured logger for console and optional file logging."""
    logger_instance = logging.getLogger("agente_arca")
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger_instance.setLevel(log_level)

    # Avoid duplicate handlers if already setup
    if logger_instance.handlers:
        return logger_instance

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger_instance.addHandler(console_handler)

    # Optional File Handler
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger_instance.addHandler(file_handler)

    # Add sensitive filter
    clave_fiscal = os.getenv("ARCA_CLAVE_FISCAL", "")
    if clave_fiscal:
        logger_instance.addFilter(SensitiveFilter([clave_fiscal]))

    return logger_instance


logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))
