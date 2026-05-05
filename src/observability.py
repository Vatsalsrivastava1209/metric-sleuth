"""
observability.py
================
Lightweight structured logging helpers for the API layer.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any

_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


def set_request_id(request_id: str | None) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def ensure_request_id() -> str:
    request_id = get_request_id()
    if request_id:
        return request_id
    generated = uuid.uuid4().hex
    set_request_id(generated)
    return generated


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a structured log line with the current request id when available."""
    payload: dict[str, Any] = {"event": event, **fields}
    request_id = get_request_id()
    if request_id:
        payload["request_id"] = request_id
    logger.info("%s", payload)
