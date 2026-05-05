from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd


class MetaAdsConnector:
    """Meta Ads Insights connector using a system-user or long-lived access token."""

    CONNECTOR_TYPE = "meta_ads"
    DISPLAY_NAME = "Meta Ads"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(
        self,
        ad_account_id: str,
        access_token: str,
        api_version: str | None = None,
        lookback_days: int = 90,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        if not ad_account_id:
            return False, "ad_account_id is required."
        if not access_token:
            return False, "access_token is required."
        normalized_account = str(ad_account_id).replace("act_", "")
        self._config = {
            "ad_account_id": normalized_account,
            "access_token": access_token,
            "api_version": api_version or os.getenv("META_API_VERSION", "v21.0"),
            "lookback_days": int(lookback_days or 90),
            **kwargs,
        }
        return True, "Meta Ads connector configured."

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"https://graph.facebook.com/{self._config['api_version']}/{path.lstrip('/')}"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params={**params, "access_token": self._config["access_token"]})
            response.raise_for_status()
            return response.json()

    def test_connection(self) -> tuple[bool, str]:
        try:
            data = self._get(f"act_{self._config['ad_account_id']}", {"fields": "name,account_status"})
            return True, f"Connected to Meta Ads account {data.get('name') or self._config['ad_account_id']}."
        except Exception as exc:
            return False, f"Meta Ads connection failed: {exc}"

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        del query
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(self._config.get("lookback_days", 90)))
        params = {
            "fields": "date_start,spend,clicks,impressions,actions,action_values",
            "time_increment": 1,
            "time_range": {"since": start_date.isoformat(), "until": end_date.isoformat()},
            "limit": 500,
        }
        rows: list[dict[str, Any]] = []
        next_url: str | None = None
        while True:
            if next_url:
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(next_url)
                    response.raise_for_status()
                    payload = response.json()
            else:
                payload = self._get(f"act_{self._config['ad_account_id']}/insights", params)
            for item in payload.get("data") or []:
                actions = {entry.get("action_type"): float(entry.get("value", 0)) for entry in item.get("actions", [])}
                values = {entry.get("action_type"): float(entry.get("value", 0)) for entry in item.get("action_values", [])}
                purchases = actions.get("purchase") or actions.get("omni_purchase") or 0.0
                revenue = values.get("purchase") or values.get("omni_purchase") or 0.0
                clicks = float(item.get("clicks") or 0)
                rows.append(
                    {
                        "date": item.get("date_start"),
                        "revenue": revenue,
                        "traffic": clicks,
                        "orders": purchases,
                        "conversion_rate": purchases / clicks if clicks else 0.0,
                        "region": "Unknown",
                        "device": "Unknown",
                        "traffic_source": "Meta Ads",
                    }
                )
            next_url = ((payload.get("paging") or {}).get("next"))
            if not next_url:
                break
        return pd.DataFrame(rows)

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, **self._config}
