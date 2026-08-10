"""Logging helpers for request correlation and optional JSON output."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_context: ContextVar[str] = ContextVar("img2sdtxt_request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Format standard logging records as one JSON object per line."""

    _EXTRA_FIELDS = ("method", "path", "status", "duration_ms", "provider", "model", "mode")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_context.get(),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int, json_format: bool = False) -> None:
    """Configure the root handler while preserving the existing text format by default."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if json_format:
        for handler in logging.getLogger().handlers:
            handler.setFormatter(JsonFormatter())
