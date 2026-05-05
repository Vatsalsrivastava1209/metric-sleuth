from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd


class GA4Connector:
    """Google Analytics Data API connector using a supplied OAuth access token."""

    CONNECTOR_TYPE = "ga4"
    DISPLAY_NAME = "Google Analytics 4"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(
        self,
        property_id: str,
        access_token: str,
        lookback_days: int = 90,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        if not property_id:
            return False, "property_id is required."
        if not access_token:
            return False, "access_token is required."
        self._config = {
            "property_id": str(property_id).replace("properties/", ""),
            "access_token": access_token,
            "lookback_days": int(lookback_days or 90),
            **kwargs,
        }
        return True, "GA4 connector configured."

    def _run_report(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{self._config['property_id']}:runReport"
        headers = {"Authorization": f"Bearer {self._config['access_token']}"}
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            return response.json()

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._run_report(
                {
                    "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
                    "metrics": [{"name": "sessions"}],
                    "limit": 1,
                }
            )
            return True, "Connected to GA4 Data API."
        except Exception as exc:
            return False, f"GA4 connection failed: {exc}"

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        del query
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(self._config.get("lookback_days", 90)))
        body = {
            "dateRanges": [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}],
            "dimensions": [
                {"name": "date"},
                {"name": "sessionDefaultChannelGroup"},
                {"name": "country"},
                {"name": "deviceCategory"},
            ],
            "metrics": [
                {"name": "totalRevenue"},
                {"name": "sessions"},
                {"name": "transactions"},
                {"name": "purchaseRevenue"},
            ],
            "limit": 100000,
        }
        payload = self._run_report(body)
        rows: list[dict[str, Any]] = []
        for row in payload.get("rows") or []:
            dims = [value.get("value", "") for value in row.get("dimensionValues", [])]
            metrics = [value.get("value", "0") for value in row.get("metricValues", [])]
            date_raw = dims[0] if dims else ""
            date_value = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(date_raw) == 8 else date_raw
            revenue = float(metrics[0] or 0)
            sessions = float(metrics[1] or 0)
            transactions = float(metrics[2] or 0)
            rows.append(
                {
                    "date": date_value,
                    "revenue": revenue,
                    "traffic": sessions,
                    "orders": transactions,
                    "conversion_rate": transactions / sessions if sessions else 0.0,
                    "traffic_source": dims[1] if len(dims) > 1 else "Unknown",
                    "region": dims[2] if len(dims) > 2 else "Unknown",
                    "device": dims[3] if len(dims) > 3 else "Unknown",
                }
            )
        return pd.DataFrame(rows)

    def quality_check(self, df: pd.DataFrame):
        """Run freshness and completeness checks on a fetched DataFrame.

        Returns a ConnectorQualityReport with GA4-specific caveats (24-48h
        conversion lag, sampling on large properties) pre-populated.
        """
        from src.connectors.quality import run_quality_check
        return run_quality_check(df, connector_type=self.CONNECTOR_TYPE)

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, **self._config}
