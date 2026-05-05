"""
connectors/__init__.py
======================
Connector registry for MetricSleuth data sources.

Usage
-----
    from src.connectors import get_connector

    connector = get_connector("postgres")
    connector.connect(host="...", port=5432, database="...", user="...", password="...")
    df = connector.fetch_data("SELECT * FROM metrics LIMIT 1000")
"""

from __future__ import annotations

import pandas as pd

from src.connectors.csv_connector      import CSVConnector
from src.connectors.postgres_connector import PostgresConnector
from src.connectors.mysql_connector    import MySQLConnector
from src.connectors.bigquery_connector import BigQueryConnector
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.ga4_connector import GA4Connector
from src.connectors.meta_ads_connector import MetaAdsConnector
from src.connectors.google_ads_connector import GoogleAdsConnector
from src.connectors.klaviyo_connector import KlaviyoConnector

_REGISTRY = {
    "csv":      CSVConnector,
    "postgres": PostgresConnector,
    "mysql":    MySQLConnector,
    "bigquery": BigQueryConnector,
    "shopify":  ShopifyConnector,
    "ga4":      GA4Connector,
    "meta_ads": MetaAdsConnector,
    "google_ads": GoogleAdsConnector,
    "klaviyo": KlaviyoConnector,
}

CONNECTOR_TYPES = list(_REGISTRY.keys())


def get_connector(connector_type: str):
    """Return an instantiated connector for the given type."""
    cls = _REGISTRY.get(connector_type.lower())
    if cls is None:
        raise ValueError(
            f"Unknown connector type '{connector_type}'. "
            f"Available: {CONNECTOR_TYPES}"
        )
    return cls()


def load_dataset_from_connector(
    dataset_id: str,
    user_id: str,
    access_token: str | None = None,
) -> pd.DataFrame:
    """Hydrate a saved dataset by reconnecting through its registered connector."""
    import io

    from src.db import download_user_dataset_bytes, get_dataset_runtime_config, USER_DATASET_BUCKET
    from src.schema_mapper import apply_mapping

    dataset = get_dataset_runtime_config(dataset_id, user_id, access_token)
    if not dataset:
        raise ValueError(f"Dataset '{dataset_id}' was not found for the current user.")

    connector_type = str(dataset.get("connector_type", "")).lower()
    schema_mapping = dataset.get("schema_mapping") or {}
    config = dataset.get("connection_config") or {}

    if connector_type == "csv":
        storage_key = config.get("storage_key")
        storage_bucket = config.get("storage_bucket")
        file_type = str(config.get("file_type", "csv")).lower()
        if not storage_key or storage_bucket != USER_DATASET_BUCKET:
            raise ValueError(
                f"Dataset '{dataset_id}' is missing its durable storage reference."
            )

        file_bytes = download_user_dataset_bytes(str(storage_key))
        if file_type in {"xlsx", "xls", "excel"}:
            df_raw = pd.read_excel(io.BytesIO(file_bytes))
        else:
            df_raw = pd.read_csv(io.BytesIO(file_bytes))
        return apply_mapping(df_raw, schema_mapping) if schema_mapping else df_raw

    query = config.get("query")
    if not query:
        raise ValueError(
            f"Dataset '{dataset_id}' is missing a saved query and cannot be reloaded."
        )

    connector = get_connector(connector_type)
    connect_kwargs = {k: v for k, v in config.items() if k not in {"query", "connector_type"}}
    ok, message = connector.connect(**connect_kwargs)
    if not ok:
        raise RuntimeError(message)

    try:
        df_raw = connector.fetch_data(str(query))
    finally:
        close = getattr(connector, "close", None)
        if callable(close):
            close()

    return apply_mapping(df_raw, schema_mapping) if schema_mapping else df_raw
