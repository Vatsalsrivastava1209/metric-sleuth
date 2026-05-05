from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd


class ShopifyConnector:
    """Token-based Shopify Admin API connector.

    This is intentionally token-based rather than OAuth-app based. It lets
    agencies connect private/custom-app tokens now while leaving marketplace
    OAuth approval as a later hardening step.
    """

    CONNECTOR_TYPE = "shopify"
    DISPLAY_NAME = "Shopify"

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(
        self,
        shop_domain: str,
        access_token: str,
        api_version: str | None = None,
        lookback_days: int = 90,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        if not shop_domain or ".myshopify.com" not in shop_domain:
            return False, "shop_domain must look like '<store>.myshopify.com'."
        if not access_token:
            return False, "access_token is required."
        self._config = {
            "shop_domain": shop_domain.strip().replace("https://", "").replace("http://", "").strip("/"),
            "access_token": access_token,
            "api_version": api_version or os.getenv("SHOPIFY_API_VERSION", "2025-10"),
            "lookback_days": int(lookback_days or 90),
            **kwargs,
        }
        return True, "Shopify connector configured."

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        url = (
            f"https://{self._config['shop_domain']}/admin/api/"
            f"{self._config['api_version']}/graphql.json"
        )
        headers = {
            "X-Shopify-Access-Token": self._config["access_token"],
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json={"query": query, "variables": variables or {}})
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(payload["errors"])
            return payload.get("data") or {}

    def test_connection(self) -> tuple[bool, str]:
        try:
            data = self._graphql("query { shop { name myshopifyDomain } }")
            shop = data.get("shop") or {}
            return True, f"Connected to Shopify store {shop.get('name') or shop.get('myshopifyDomain')}."
        except Exception as exc:
            return False, f"Shopify connection failed: {exc}"

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        del query
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=int(self._config.get("lookback_days", 90)))
        search = f"created_at:>={start_date.isoformat()} created_at:<={end_date.isoformat()}"
        graphql = """
        query Orders($cursor: String, $search: String!) {
          orders(first: 250, after: $cursor, query: $search, sortKey: CREATED_AT) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                createdAt
                sourceName
                totalPriceSet { shopMoney { amount } }
                customer { defaultAddress { countryCode } }
              }
            }
          }
        }
        """
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            data = self._graphql(graphql, {"cursor": cursor, "search": search})
            orders = data.get("orders") or {}
            for edge in orders.get("edges") or []:
                node = edge.get("node") or {}
                created_at = str(node.get("createdAt") or "")[:10]
                amount = ((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0
                address = ((node.get("customer") or {}).get("defaultAddress") or {})
                rows.append(
                    {
                        "date": created_at,
                        "revenue": float(amount),
                        "orders": 1,
                        "traffic": 1,
                        "conversion_rate": 1.0,
                        "region": address.get("countryCode") or "Unknown",
                        "device": "Unknown",
                        "traffic_source": node.get("sourceName") or "Shopify",
                    }
                )
            page_info = orders.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if not rows:
            return pd.DataFrame(columns=["date", "revenue", "traffic", "orders", "conversion_rate", "region", "device", "traffic_source"])

        df = pd.DataFrame(rows)
        grouped = (
            df.groupby(["date", "region", "device", "traffic_source"], as_index=False)
            .agg({"revenue": "sum", "orders": "sum", "traffic": "sum"})
        )
        grouped["conversion_rate"] = grouped["orders"] / grouped["traffic"].clip(lower=1)
        return grouped

    def quality_check(self, df: pd.DataFrame):
        """Run freshness and completeness checks on a fetched DataFrame.

        Shopify is near-real-time (webhooks), so staleness > 6h is a warning.
        """
        from src.connectors.quality import run_quality_check
        return run_quality_check(df, connector_type=self.CONNECTOR_TYPE)

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, **self._config}
