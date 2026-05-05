from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd


class GoogleAdsConnector:
    """Google Ads API connector using developer token plus OAuth access token."""

    CONNECTOR_TYPE = "google_ads"
    DISPLAY_NAME = "Google Ads"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(
        self,
        customer_id: str,
        access_token: str,
        developer_token: str,
        login_customer_id: str = "",
        api_version: str | None = None,
        lookback_days: int = 90,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        if not customer_id:
            return False, "customer_id is required."
        if not access_token:
            return False, "access_token is required."
        if not developer_token:
            return False, "developer_token is required."
        self._config = {
            "customer_id": str(customer_id).replace("-", ""),
            "access_token": access_token,
            "developer_token": developer_token,
            "login_customer_id": str(login_customer_id).replace("-", "") if login_customer_id else "",
            "api_version": api_version or os.getenv("GOOGLE_ADS_API_VERSION", "v18"),
            "lookback_days": int(lookback_days or 90),
            **kwargs,
        }
        return True, "Google Ads connector configured."

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config['access_token']}",
            "developer-token": self._config["developer_token"],
            "Content-Type": "application/json",
        }
        if self._config.get("login_customer_id"):
            headers["login-customer-id"] = self._config["login_customer_id"]
        return headers

    def _search_stream(self, query: str) -> list[dict[str, Any]]:
        url = (
            f"https://googleads.googleapis.com/{self._config['api_version']}/customers/"
            f"{self._config['customer_id']}/googleAds:searchStream"
        )
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=self._headers(), json={"query": query})
            response.raise_for_status()
            payload = response.json()
        rows: list[dict[str, Any]] = []
        for chunk in payload:
            rows.extend(chunk.get("results") or [])
        return rows

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._search_stream("SELECT customer.id FROM customer LIMIT 1")
            return True, "Connected to Google Ads API."
        except Exception as exc:
            return False, f"Google Ads connection failed: {exc}"

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        del query
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(self._config.get("lookback_days", 90)))
        gaql = f"""
            SELECT
              segments.date,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value,
              metrics.cost_micros
            FROM customer
            WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
        """
        rows: list[dict[str, Any]] = []
        for result in self._search_stream(gaql):
            segments = result.get("segments") or {}
            metrics = result.get("metrics") or {}
            clicks = float(metrics.get("clicks") or 0)
            conversions = float(metrics.get("conversions") or 0)
            rows.append(
                {
                    "date": segments.get("date"),
                    "revenue": float(metrics.get("conversionsValue") or metrics.get("conversions_value") or 0),
                    "traffic": clicks,
                    "orders": conversions,
                    "conversion_rate": conversions / clicks if clicks else 0.0,
                    "region": "Unknown",
                    "device": "Unknown",
                    "traffic_source": "Google Ads",
                }
            )
        return pd.DataFrame(rows)

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, **self._config}
