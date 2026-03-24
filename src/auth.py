"""
auth.py
=======
Supabase authentication wrapper for MetricSleuth SaaS.

Provides login, signup, logout, session management, and a Streamlit-aware
auth guard that redirects unauthenticated users to the login page.

Usage
-----
    from src.auth import require_auth, login, signup, logout, get_current_user

    # In any page file:
    user = require_auth()   # returns user dict or stops execution
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)


# ── Supabase client (lazy init) ───────────────────────────────────────────────

def _get_client():
    """Return a Supabase client using credentials from Streamlit secrets / env."""
    try:
        from supabase import create_client, Client  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "supabase-py is not installed. Run: pip install supabase"
        ) from exc

    import os
    from dotenv import load_dotenv
    load_dotenv()

    url = ""
    key = ""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_ANON_KEY", "")
    except Exception:
        pass
        
    url = url or os.getenv("SUPABASE_URL", "")
    key = key or os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        st.error(
            "⚠️ Supabase credentials not found.  "
            "Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to `.streamlit/secrets.toml` or your environment."
        )
        st.stop()

    return create_client(url, key)


# ── Session helpers ───────────────────────────────────────────────────────────

_SESSION_KEY = "ms_user"


def _set_session(user: dict | None) -> None:
    st.session_state[_SESSION_KEY] = user


def get_current_user() -> dict | None:
    """Return the currently logged-in user dict, or None."""
    return st.session_state.get(_SESSION_KEY)


def is_authenticated() -> bool:
    return get_current_user() is not None


# ── Auth operations ───────────────────────────────────────────────────────────

def login(email: str, password: str) -> tuple[bool, str]:
    """
    Authenticate with Supabase email + password.

    Returns (success: bool, message: str).
    On success, stores user in session state.
    """
    client = _get_client()
    try:
        response = client.auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
        user = response.user
        if user is None:
            return False, "Invalid credentials."

        # Load profile (tier, etc.)
        profile = _load_profile(client, user.id)

        _set_session({
            "id":    user.id,
            "email": user.email,
            "tier":  profile.get("subscription_tier", "free"),
            "profile": profile,
            # Store access token for service calls
            "access_token": response.session.access_token,
        })
        logger.info("User %s logged in.", user.email)
        return True, "Welcome back!"

    except Exception as exc:
        logger.warning("Login failed: %s", exc)
        msg = str(exc)
        if "Invalid login credentials" in msg:
            return False, "Incorrect email or password."
        if "Email not confirmed" in msg:
            return False, "Please confirm your email before logging in."
        return False, f"Login error: {msg}"


def signup(email: str, password: str, full_name: str = "") -> tuple[bool, str]:
    """
    Create a new Supabase account.

    Returns (success: bool, message: str).
    Supabase sends a confirmation email automatically.
    """
    client = _get_client()
    try:
        response = client.auth.sign_up(
            {
                "email":    email.strip(),
                "password": password,
                "options":  {"data": {"full_name": full_name}},
            }
        )
        user = response.user
        if user is None:
            return False, "Signup failed — please try again."

        logger.info("New user signed up: %s", email)
        return True, (
            "Account created! Check your email for a confirmation link, "
            "then log in."
        )
    except Exception as exc:
        logger.warning("Signup failed: %s", exc)
        msg = str(exc)
        if "already registered" in msg.lower() or "user already exists" in msg.lower():
            return False, "An account with this email already exists."
        if "password" in msg.lower() and "characters" in msg.lower():
            return False, "Password must be at least 6 characters."
        return False, f"Signup error: {msg}"


def logout() -> None:
    """Sign out and clear the session."""
    client = _get_client()
    try:
        client.auth.sign_out()
    except Exception:
        pass
    _set_session(None)
    # Clear all session state to avoid stale data across users
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    logger.info("User logged out.")


# ── Profile helpers ───────────────────────────────────────────────────────────

def _load_profile(client, user_id: str) -> dict:
    """Fetch the profiles row for a given user ID."""
    try:
        result = (
            client.table("profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return result.data or {}
    except Exception as exc:
        logger.warning("Could not load profile for %s: %s", user_id, exc)
        return {}


def refresh_profile() -> None:
    """Reload the current user's profile from Supabase (e.g. after billing upgrade)."""
    user = get_current_user()
    if not user:
        return
    client = _get_client()
    profile = _load_profile(client, user["id"])
    user["tier"]    = profile.get("subscription_tier", "free")
    user["profile"] = profile
    _set_session(user)


def get_user_tier() -> str:
    """Return the current user's subscription tier ('free' | 'pro' | 'business')."""
    user = get_current_user()
    return user.get("tier", "free") if user else "free"


# ── Streamlit auth guard ──────────────────────────────────────────────────────

def require_auth() -> dict:
    """
    Streamlit auth guard.

    Call at the top of any page that requires authentication.
    - If authenticated:  returns the user dict and execution continues.
    - If NOT authenticated: renders a friendly message and calls st.stop().

    Example
    -------
        user = require_auth()
        st.write(f"Hello {user['email']}")
    """
    user = get_current_user()
    if user:
        return user

    st.markdown(
        """
        <div style="text-align:center;padding:4rem 2rem;">
            <div style="font-size:2rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>
            <p style="color:#3a4a6b;margin-top:.5rem;font-size:.9rem;">
                Please log in to access this page.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Login", type="primary"):
        st.switch_page("Home.py")
    st.stop()
    return {}  # unreachable — satisfies type checker


# ── Tier badge ────────────────────────────────────────────────────────────────

TIER_COLORS = {
    "free":     "#3a4a6b",
    "pro":      "#00e5ff",
    "business": "#7b68ee",
}

TIER_LABELS = {
    "free":     "FREE",
    "pro":      "PRO",
    "business": "BUSINESS",
}


def render_tier_badge() -> None:
    """Render a small tier badge in the Streamlit sidebar."""
    tier  = get_user_tier()
    color = TIER_COLORS.get(tier, "#3a4a6b")
    label = TIER_LABELS.get(tier, tier.upper())
    st.sidebar.markdown(
        f'<span style="background:{color}20;color:{color};border:1px solid {color}40;'
        f'border-radius:4px;padding:2px 10px;font-size:.65rem;letter-spacing:2px;'
        f'font-family:JetBrains Mono,monospace;font-weight:700;">{label}</span>',
        unsafe_allow_html=True,
    )
