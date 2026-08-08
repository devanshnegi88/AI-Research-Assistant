"""
Logging configuration.

Provides `setup_logging()` to be called once at app startup, and a
`get_logger(name)` helper for module-level loggers. Supports plain-text
(local/dev) and JSON (staging/production) output, controlled via
`settings.LOG_JSON`.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """Renders each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Attach any extra fields passed via logger.info(..., extra={...})
        reserved = logging.LogRecord(
            "", 0, "", 0, "", (), None
        ).__dict__.keys()
        for key, value in record.__dict__.items():
            if key not in reserved and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Configure the root logger once, at process startup."""

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    # Avoid duplicate handlers on reload
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_JSON:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DB_ECHO else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Module-level logger accessor — use `get_logger(__name__)`."""
    return logging.getLogger(name)
