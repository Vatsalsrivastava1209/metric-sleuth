"""
scripts/mock_webhook_server.py
================================
A self-contained, zero-dependency staging server that mounts ONLY the
/api/v1/webhooks/stripe endpoint from the real MetricSleuth codebase,
but replaces the Supabase `get_admin_client()` with a fast mock that
logs DB mutations without making real network calls.

This lets you:
  - Run the actual webhook handler logic (signature check, routing, etc.)
  - Fire the stress-tester against it
  - Validate correct event handling without any live Supabase / Stripe credentials

Usage:
    python scripts/mock_webhook_server.py          # listens on :8000

The server is intentionally single-file and dependency-light.
Only requires: fastapi, uvicorn, stripe

    pip install fastapi "uvicorn[standard]" stripe
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from collections import defaultdict
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ── Project root on sys.path ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Set required env vars BEFORE any module imports (so webhooks.py reads them)
TEST_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_test_stress_test_secret_key_1234")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", TEST_SECRET)
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_mock")
os.environ.setdefault("STRIPE_PRICE_PRO", "price_test_pro_monthly")
os.environ.setdefault("STRIPE_PRICE_BUSINESS", "price_test_business_monthly")

# ── In-memory DB mock ─────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("mock_server")

# Thread-safe in-memory "database" for profiling updates during stress tests
_db_lock = threading.Lock()
_profiles: dict[str, dict] = {}  # customer_id → profile state
_write_log: list[dict] = []       # ordered log of all DB writes


def _get_mock_admin_client():
    """Return a mock Supabase client that stores writes in memory."""

    class _MockTable:
        def __init__(self, table_name: str):
            self._table = table_name
            self._filters: dict = {}
            self._updates: dict = {}

        def update(self, data: dict):
            self._updates = data
            return self

        def eq(self, col: str, val: str):
            self._filters[col] = val
            return self

        def execute(self):
            with _db_lock:
                write_entry = {
                    "table": self._table,
                    "filters": dict(self._filters),
                    "updates": dict(self._updates),
                }
                _write_log.append(write_entry)
                # Update the in-memory profile if it's a profile write
                if self._table == "profiles":
                    key = (
                        self._filters.get("stripe_customer_id")
                        or self._filters.get("id")
                        or "unknown"
                    )
                    if key not in _profiles:
                        _profiles[key] = {}
                    _profiles[key].update(self._updates)
                    logger.debug(
                        "MOCK DB | profiles[%s] → %s",
                        key,
                        json.dumps(self._updates, default=str),
                    )
                else:
                    logger.debug("MOCK DB | %s write: %s", self._table, self._updates)

            class _FakeResult:
                data = []
                count = 0
            return _FakeResult()

    class _MockClient:
        def table(self, name: str):
            return _MockTable(name)

    return _MockClient()


# ── Monkey-patch get_admin_client BEFORE importing webhooks ───────────────────
import api.dependencies as _deps
_deps.get_admin_client = _get_mock_admin_client  # type: ignore

# Now safe to import the real webhook router
from api.routers.webhooks import router as webhook_router

# ── FastAPI app assembly ───────────────────────────────────────────────────────
app = FastAPI(
    title="MetricSleuth — Mock Webhook Staging Server",
    description="Lightweight staging server for webhook stress testing. No real Supabase/Stripe credentials needed.",
    version="1.0.0",
)
app.include_router(webhook_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "server": "mock_webhook_staging"}


@app.get("/api/v1/webhooks/debug/writes")
async def debug_writes():
    """Return all DB writes recorded so far. Useful for verifying test assertions."""
    with _db_lock:
        return {
            "total_writes": len(_write_log),
            "profile_states": {k: v for k, v in _profiles.items()},
            "write_log": _write_log[-50:],  # last 50 entries
        }


@app.delete("/api/v1/webhooks/debug/reset")
async def debug_reset():
    """Clear the in-memory DB state. Call between test suites."""
    with _db_lock:
        _profiles.clear()
        _write_log.clear()
    return {"status": "reset"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info("Starting mock webhook staging server on port %d", port)
    logger.info("STRIPE_WEBHOOK_SECRET: %s", TEST_SECRET[:30] + "...")
    logger.info("Price map: PRO=%s  BUSINESS=%s",
                os.environ.get("STRIPE_PRICE_PRO"),
                os.environ.get("STRIPE_PRICE_BUSINESS"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
