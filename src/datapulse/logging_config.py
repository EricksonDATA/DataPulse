"""Structured logging configuration for DataPulse."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Outputs log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge extra fields attached via logging.LoggerAdapter or extra={}
        for key in (
            "run_id",
            "pipeline",
            "dataset",
            "contract_version",
            "check_type",
            "status",
            "duration_ms",
            "source_row_count",
            "target_row_count",
            "error_type",
        ):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure DataPulse structured logging.

    Returns the root datapulse logger. Logs to stdout as JSON.
    Never logs credentials, tokens, or source payloads.
    """
    logger = logging.getLogger("datapulse")
    logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Prevent propagation to root logger (avoids duplicate output)
    logger.propagate = False

    return logger
