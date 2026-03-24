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

from src.connectors.csv_connector      import CSVConnector
from src.connectors.postgres_connector import PostgresConnector
from src.connectors.mysql_connector    import MySQLConnector
from src.connectors.bigquery_connector import BigQueryConnector

_REGISTRY = {
    "csv":      CSVConnector,
    "postgres": PostgresConnector,
    "mysql":    MySQLConnector,
    "bigquery": BigQueryConnector,
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
