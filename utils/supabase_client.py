"""
utils/supabase_client.py
========================
Process-scoped Supabase client singletons.

Why singletons matter
---------------------
The Python Supabase SDK (supabase-py) wraps the PostgREST HTTP client. Every
call to ``create_client()`` allocates a new ``httpx.Client`` with its own
connection pool. Under 4–8 Celery workers each running a multi-stage pipeline
(load → detect → segment → correlate → persist), every stage was previously
calling ``get_admin_client()`` which created a fresh client object. This meant
potentially 50–100+ open TCP connections to the Supabase PostgREST endpoint
simultaneously on a burst.

The fix: ``lru_cache(maxsize=1)`` on factory functions makes the client
process-scoped (one per Celery worker process, one per FastAPI process). The
connection pool is reused across all calls within the same process.

Thread safety
-------------
``lru_cache`` is thread-safe in CPython for reads once the cache is populated.
The first call may race in a multithreaded context (e.g., FastAPI under
concurrent requests) but ``create_client`` is idempotent — the worst case is
two clients are created and one is discarded. Subsequent calls are lock-free.

Per-user RLS scoping
--------------------
The singleton clients use the ANON or SERVICE_ROLE key. For authenticated user
requests, call ``client.postgrest.auth(access_token)`` on the singleton before
issuing the query. For background worker writes, call ``_impersonate_user``
(src/db.py) to set the Postgres session claim.

IMPORTANT: Do not store the result of ``client.postgrest.auth(token)`` — that
method mutates the client in place and returns self. Always call auth() inside
the same function that issues the query, never at module level.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_anon_singleton():
    """Return the process-scoped Supabase anon-key client.

    Suitable for user-authenticated requests where the JWT is forwarded via
    ``client.postgrest.auth(access_token)`` before each query.

    Returns
    -------
    supabase.Client
        Singleton client using SUPABASE_ANON_KEY.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise ImportError("Run: pip install supabase") from exc

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_service_singleton():
    """Return the process-scoped Supabase service-role client.

    Bypasses RLS by default. Always pair with ``_impersonate_user()`` (src/db.py)
    for background writes that must respect per-user tenant isolation.

    Returns
    -------
    supabase.Client
        Singleton client using SUPABASE_SERVICE_KEY.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise ImportError("Run: pip install supabase") from exc

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)
