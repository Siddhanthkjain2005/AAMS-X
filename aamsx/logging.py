"""Structured logging.

Small enough to avoid a dependency, structured enough to be greppable:
every record is emitted as a single line of JSON on stderr, with the extra
keyword arguments merged into the payload.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_RESERVED = frozenset(
    [
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
    ]
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    _COLOURS = {"DEBUG": "\033[2m", "INFO": "\033[36m", "WARNING": "\033[33m", "ERROR": "\033[31m"}

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        reset = "\033[0m" if colour else ""
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        suffix = " " + " ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        return f"{colour}{stamp} {record.levelname:<7}{reset} {record.getMessage()}{suffix}"


def configure_logging(level: str | int | None = None, *, json_output: bool | None = None) -> None:
    """Idempotently install the AAMS-X log handler on the root logger."""
    resolved = level or os.environ.get("AAMSX_LOG_LEVEL", "INFO")
    as_json = json_output if json_output is not None else os.environ.get("AAMSX_LOG_JSON") == "1"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if as_json else HumanFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_aamsx", False):
            root.removeHandler(existing)
    handler._aamsx = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(resolved)
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    for chatty in ("httpx", "httpcore", "urllib3", "matplotlib", "PIL"):
        logging.getLogger(chatty).setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
