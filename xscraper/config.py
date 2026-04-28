"""xscraper configuration loader with default-fallback logging."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment at module import time (idempotent)
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)


class _JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format record as JSON with level, logger, msg fields."""
        log_obj = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(log_obj, separators=(",", ":"))


@dataclass(frozen=True)
class Config:
    """xscraper configuration."""

    x_username: str | None
    x_password: str | None
    state_path: Path
    log_format: str  # "json" or "text"


def load_config() -> Config:
    """Load xscraper config from environment with defaults and fallback logging.

    - STATE_PATH: default to Path("xscraper/state.json"), log INFO if fallback
    - LOG_FORMAT: default to "json", log INFO if fallback
    - X_USERNAME/X_PASSWORD: return None if not set (no logging)

    Returns:
        Config dataclass with all fields populated.
    """
    # Read optional credentials
    x_username = os.getenv("X_USERNAME")
    x_password = os.getenv("X_PASSWORD")

    # Read STATE_PATH with default fallback
    state_path_str = os.getenv("STATE_PATH")
    if state_path_str:
        state_path = Path(state_path_str)
    else:
        state_path = Path("xscraper/state.json")
        logger.info("STATE_PATH not set in env, using default xscraper/state.json")

    # Read LOG_FORMAT with default fallback
    log_format = os.getenv("LOG_FORMAT")
    if log_format:
        # Use the value from env
        pass
    else:
        log_format = "json"
        logger.info("LOG_FORMAT not set in env, using default json")

    return Config(
        x_username=x_username,
        x_password=x_password,
        state_path=state_path,
        log_format=log_format,
    )


def setup_logging(log_format: str) -> None:
    """Configure stderr logging for xscraper.

    Idempotent: safe to call multiple times (removes old handlers).
    Sets logger level to INFO.

    Args:
        log_format: "json" or "text"
    """
    xscraper_logger = logging.getLogger("xscraper")
    xscraper_logger.setLevel(logging.INFO)

    # Remove any existing handlers to ensure idempotence
    xscraper_logger.handlers.clear()

    # Create stderr handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)

    # Set formatter based on format
    if log_format == "json":
        formatter = _JsonFormatter()
    else:  # "text"
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")

    handler.setFormatter(formatter)
    xscraper_logger.addHandler(handler)
