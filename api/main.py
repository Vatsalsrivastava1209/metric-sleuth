"""
api/main.py
============
FastAPI application entry point for MetricSleuth.

Security Headers
----------------
All responses include a suite of OWASP-recommended security headers:
  - Strict-Transport-Security (HSTS): forces HTTPS for 1 year.
  - X-Content-Type-Options: nosniff — prevents MIME-type sniffing attacks.
  - X-Frame-Options: DENY — prevents clickjacking.
  - X-XSS-Protection: 1; mode=block — legacy XSS filter for older browsers.
  - Referrer-Policy: strict-origin-when-cross-origin — limits referrer leakage.
  - Content-Security-Policy: restricts resource loading origins.
  - Permissions-Policy: disables unnecessary browser features.

CORS
----
Allowed origins are read from the CORS_ORIGINS environment variable
(comma-separated). Never use "*" in production — set the actual frontend URL.

OpenAPI Docs
------------
Docs are disabled in production (DOCS_ENABLED=false env var).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from src.observability import set_request_id
from utils.config import MAX_UPLOAD_SIZE_BYTES

# ── Application factory ───────────────────────────────────────────────────────

_docs_enabled = os.getenv("DOCS_ENABLED", "true").lower() == "true"

app = FastAPI(
    title="MetricSleuth API",
    description="Decoupled backend for MetricSleuth SaaS — Enterprise Edition",
    version="2.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# ── Payload Size Limit middleware ─────────────────────────────────────────────

# Hard limit on raw payload bytes. This must match the documented upload ceiling.
_MAX_PAYLOAD_BYTES = MAX_UPLOAD_SIZE_BYTES

@app.middleware("http")
async def limit_content_length(request: Request, call_next: Callable) -> Response:
    """Enforce a strict memory bound on request bodies before Uvicorn parsing."""
    if request.method in ("POST", "PUT", "PATCH"):
        content_length_str = request.headers.get("content-length")
        is_chunked = request.headers.get("transfer-encoding", "").lower() == "chunked"
        
        if content_length_str and content_length_str.isdigit():
            if int(content_length_str) > _MAX_PAYLOAD_BYTES:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Payload exceeds maximum allowed size of {_MAX_PAYLOAD_BYTES / (1024*1024):.0f}MB."}
                )
        elif is_chunked or not content_length_str:
            # P1: Prevent chunked encoding memory exhaustion attacks
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=411,
                content={"detail": "Content-Length header is required. Chunked transfer encoding is not supported."}
            )
    return await call_next(request)

# ── Security headers middleware ───────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable) -> Response:
    """Inject OWASP-recommended security headers on every response.

    These headers are checked by enterprise security teams and penetration
    testers as part of standard HTTP security audits. Without them, the API
    fails basic OWASP ZAP / BurpSuite scans.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    set_request_id(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        set_request_id(None)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

    # Prevent downgrade attacks — require HTTPS for 1 year including subdomains
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains; preload"
    )
    # Prevent MIME-sniffing: browser must respect Content-Type as declared
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Prevent this API response being embedded in an iframe (clickjacking)
    response.headers["X-Frame-Options"] = "DENY"
    # Legacy XSS filter — still honoured by some older browsers/proxies
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Limit referrer header disclosure when navigating cross-origin
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Restrict what browser features the JavaScript in API responses can use
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=()"
    )
    # Content Security Policy — API responses are data (JSON), not HTML.
    # default-src 'none' prevents any content rendering; frame-ancestors prevents
    # embedding; upgrade-insecure-requests enforces HTTPS on any linked resources.
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; upgrade-insecure-requests"
    )
    # Remove the server fingerprint header that Uvicorn/Starlette adds by default
    if "server" in response.headers:
        del response.headers["server"]
    if "x-powered-by" in response.headers:
        del response.headers["x-powered-by"]
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-MS"] = str(duration_ms)

    return response


# ── CORS ───────────────────────────────────────────────────────────────────────

_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "x-api-key"],
)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health_check():
    """Basic liveness probe endpoint — used by Docker and load balancers."""
    return {"status": "ok", "version": "2.1.0"}


# ── Routers ───────────────────────────────────────────────────────────────────

from api.routers.analyze  import router as analyze_router
from api.routers.account import router as account_router
from api.routers.datasets import router as datasets_router
from api.routers.ingest   import router as ingest_router
from api.routers.memory   import router as memory_router
from api.routers.reports  import router as reports_router
from api.routers.webhooks import router as webhooks_router
from api.routers.export   import router as export_router

app.include_router(account_router)
app.include_router(analyze_router)
app.include_router(datasets_router)
app.include_router(ingest_router)
app.include_router(memory_router)
app.include_router(reports_router)
app.include_router(webhooks_router)
app.include_router(export_router)
