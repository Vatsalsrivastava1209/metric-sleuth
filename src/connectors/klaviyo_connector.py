from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd


class KlaviyoConnector:
    """Klaviyo connector for metric aggregate pulls using a private API key."""

    CONNECTOR_TYPE = "klaviyo"
    DISPLAY_NAME = "Klaviyo"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(
        self,
        private_key: str,
        metric_id: str = "",
        revision: str = "2024-10-15",
        lookback_days: int = 90,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        if not private_key:
            return False, "private_key is required."
        self._config = {
            "private_key": private_key,
            "metric_id": metric_id,
            "revision": revision,
            "lookback_days": int(lookback_days or 90),
            **kwargs,
        }
        return True, "Klaviyo connector configured."

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Klaviyo-API-Key {self._config['private_key']}",
            "revision": self._config.get("revision", "2024-10-15"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def test_connection(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get("https://a.klaviyo.com/api/metrics/", headers=self._headers(), params={"page[size]": 1})
                response.raise_for_status()
            return True, "Connected to Klaviyo Metrics API."
        except Exception as exc:
            return False, f"Klaviyo connection failed: {exc}"

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        del query
        metric_id = str(self._config.get("metric_id") or "")
        if not metric_id:
            raise RuntimeError("metric_id is required to fetch Klaviyo aggregate data.")

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(self._config.get("lookback_days", 90)))
        body = {
            "data": {
                "type": "metric-aggregate",
                "attributes": {
                    "metric_id": metric_id,
                    "measurements": ["count", "sum_value"],
                    "interval": "day",
                    "filter": [
                        f"greater-or-equal(datetime,{start_date.isoformat()})",
                        f"less-than(datetime,{(end_date + timedelta(days=1)).isoformat()})",
                    ],
                },
            }
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://a.klaviyo.com/api/metric-aggregates/", headers=self._headers(), json=body)
            response.raise_for_status()
            payload = response.json()

        attributes = (payload.get("data") or {}).get("attributes") or {}
        dates = attributes.get("dates") or []
        series = attributes.get("data") or {}
        counts = series.get("count") or []
        values = series.get("sum_value") or []
        rows: list[dict[str, Any]] = []
        for index, date_value in enumerate(dates):
            orders = float(counts[index] if index < len(counts) else 0)
            revenue = float(values[index] if index < len(values) else 0)
            rows.append(
                {
                    "date": str(date_value)[:10],
                    "revenue": revenue,
                    "traffic": max(orders, 1),
                    "orders": orders,
                    "conversion_rate": 1.0 if orders else 0.0,
                    "region": "Unknown",
                    "device": "Unknown",
                    "traffic_source": "Klaviyo",
                }
            )
        return pd.DataFrame(rows)

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, **self._config}
