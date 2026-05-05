"""
api/routers/account.py
======================
Authenticated account, settings, and billing endpoints for the Next.js UI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PortalRequest,
    PortalResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)
from src.billing import create_checkout_session, create_portal_session
from src.db import get_profile, update_profile
from src.observability import log_event

router = APIRouter(prefix="/api/v1/account", tags=["account"])
logger = logging.getLogger(__name__)


@router.get("/profile", response_model=ProfileResponse)
async def read_profile(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ProfileResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    profile = await asyncio.to_thread(get_profile, user_id, access_token)
    return ProfileResponse(
        id=user_id,
        email=current_user.get("email"),
        agency_name=profile.get("full_name", "") or "",
        subscription_tier=profile.get("subscription_tier", "free"),
        llm_backend=profile.get("llm_backend", "gemini"),
        llm_api_key_configured=bool(profile.get("llm_api_key") or profile.get("llm_api_key_vault_id")),
        slack_webhook_url=profile.get("slack_webhook_url", ""),
        alert_email=profile.get("alert_email", ""),
        stripe_customer_id=profile.get("stripe_customer_id", ""),
    )


@router.put("/profile", response_model=ProfileUpdateResponse)
async def write_profile(
    payload: ProfileUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ProfileUpdateResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    updates = payload.model_dump(exclude_none=True)
    if "agency_name" in updates:
        updates["full_name"] = updates.pop("agency_name")
    if not updates:
        raise HTTPException(status_code=422, detail="No profile fields were provided.")

    ok = await asyncio.to_thread(update_profile, user_id, updates, access_token)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to persist profile settings.")

    log_event(logger, "profile.updated", user_id=user_id, fields=sorted(updates.keys()))
    return ProfileUpdateResponse(status="ok", message="Profile settings updated.")


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> CheckoutResponse:
    checkout_url = await asyncio.to_thread(
        create_checkout_session,
        user_id=current_user["user_id"],
        user_email=current_user["email"],
        tier=payload.tier,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )
    if not checkout_url:
        raise HTTPException(status_code=500, detail="Could not create a Stripe checkout session.")

    log_event(
        logger,
        "billing.checkout_created",
        user_id=current_user["user_id"],
        requested_tier=payload.tier,
    )
    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/billing/portal", response_model=PortalResponse)
async def create_portal(
    payload: PortalRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> PortalResponse:
    profile = await asyncio.to_thread(
        get_profile,
        current_user["user_id"],
        current_user["access_token"],
    )
    stripe_customer_id = profile.get("stripe_customer_id", "")
    if not stripe_customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer is attached to this account.")

    portal_url = await asyncio.to_thread(create_portal_session, stripe_customer_id, payload.return_url)
    if not portal_url:
        raise HTTPException(status_code=500, detail="Could not create a Stripe billing portal session.")

    log_event(logger, "billing.portal_created", user_id=current_user["user_id"])
    return PortalResponse(portal_url=portal_url)
