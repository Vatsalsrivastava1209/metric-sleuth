import os
import asyncio
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

load_dotenv()

# We depend directly on the Authorization header formatted as: Bearer <TOKEN>
security = HTTPBearer()

# We depend on an explicit "x-api-key" header for machine-to-machine traffic
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def get_supabase_client() -> Client:
    """Instantiate a Supabase client using environment variables."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in the backend environment.")
    return create_client(url, key)

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> dict:
    """
    Dependency that extracts the JWT token from the Next.js frontend
    and verifies it against Supabase Auth.
    
    Returns the user dict if authenticated, raises 401 otherwise.
    """
    token = credentials.credentials
    client = get_supabase_client()

    def _fetch_user():
        return client.auth.get_user(token)

    # Offload the sync SDK call so concurrent authenticated requests do not block
    # the FastAPI event loop under load.
    response = await asyncio.to_thread(_fetch_user)
    
    if not response or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Extra check can go here (e.g. verifying subscription tier from `profiles` table)
    return {
        "user_id": response.user.id,
        "email": response.user.email,
        "role": response.user.role,
        "raw_token": token,
        "access_token": token,
    }

def get_admin_client() -> Client:
    """Return a Supabase client using the SERVICE_ROLE key (bypasses RLS)."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_SERVICE_KEY in environment.")
    return create_client(url, key)

async def get_api_key_user(
    api_key: Annotated[str | None, Depends(api_key_header)]
) -> dict:
    """
    Dependency that extracts the x-api-key header from automated M2M pipelines,
    hashes it, matches it directly against the DB using the Service Role,
    and returns the authorized user profile.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'x-api-key' header for M2M ingestion.",
            headers={"WWW-Authenticate": "APIKey"},
        )

    import asyncio
    import hashlib
    # We never store plaintext. Recreate the SHA256 of the incoming key.
    hashed_key = hashlib.sha256(api_key.encode('utf-8')).hexdigest()

    def _lookup_key() -> list:
        client = get_admin_client()
        result = client.table("api_keys").select("user_id").eq("key_hash", hashed_key).execute()
        return result.data or []

    data = await asyncio.to_thread(_lookup_key)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API Key.",
            headers={"WWW-Authenticate": "APIKey"},
        )

    user_id = data[0]["user_id"]
    return {
        "user_id": user_id,
        "raw_token": None,
        "m2m": True
    }

import redis.asyncio as aioredis

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_pool: aioredis.Redis | None = None

def _get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _redis_pool

async def require_pro_tier(
    current_user: Annotated[dict, Depends(get_current_user)]
) -> dict:
    """
    Backend dependency that enforces subscription gates at the API level.
    Checks the Supabase profiles table (with 5-minute Redis cache) and gates
    access to PRO and BUSINESS tier users only.

    The blocking DB call is wrapped in asyncio.to_thread so it does not
    stall the FastAPI event loop under concurrent requests.
    """
    import asyncio

    user_id = current_user["user_id"]
    redis = _get_redis()
    cache_key = f"tier_cache:{user_id}"

    # Check distributed redis cache to avoid hammering the DB on every request
    try:
        tier = await redis.get(cache_key)
    except Exception:
        tier = None

    if not tier:
        def _fetch_tier() -> str:
            client = get_admin_client()
            result = client.table("profiles").select("subscription_tier").eq("id", user_id).execute()
            if result.data:
                return result.data[0].get("subscription_tier", "free")
            return "free"

        tier = await asyncio.to_thread(_fetch_tier)
        try:
            await redis.set(cache_key, tier, ex=300)
        except Exception:
            pass

    # Grant access to PRO and BUSINESS tier subscribers
    # (business is a superset of pro — they must not be blocked here)
    if tier not in ("pro", "business"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active 'Pro' or 'Business' subscription required to access this endpoint."
        )

    current_user["tier"] = tier
    return current_user
