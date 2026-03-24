"""
postgres_connector.py
=====================
PostgreSQL connector using psycopg2.

Install:  pip install psycopg2-binary
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class PostgresConnector:
    """Connector for PostgreSQL databases."""

    CONNECTOR_TYPE = "postgres"
    DISPLAY_NAME   = "PostgreSQL"

    def __init__(self):
        self._conn = None
        self._config: dict[str, Any] = {}

    # ── Interface ─────────────────────────────────────────────────────────────

    def connect(
        self,
        host: str,
        port: int = 5432,
        database: str = "",
        user: str = "",
        password: str = "",
        **kwargs,
    ) -> tuple[bool, str]:
        """Open a connection. Returns (success, message)."""
        try:
            import psycopg2  # type: ignore
        except ImportError:
            return False, "psycopg2 not installed. Run: pip install psycopg2-binary"

        self._config = dict(
            host=host, port=port, database=database,
            user=user, password=password,
        )
        try:
            self._conn = psycopg2.connect(**self._config)
            logger.info("Postgres connected to %s:%s/%s", host, port, database)
            return True, f"Connected to {database}@{host}:{port}"
        except Exception as exc:
            logger.error("Postgres connection failed: %s", exc)
            return False, f"Connection failed: {exc}"

    def test_connection(self) -> tuple[bool, str]:
        if self._conn is None:
            return False, "Not connected."
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True, "Connection is healthy."
        except Exception as exc:
            return False, f"Connection test failed: {exc}"

    def list_tables(self) -> list[str]:
        """Return all user-accessible table names in the connected database."""
        if self._conn is None:
            return []
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema || '.' || table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY 1
                    """
                )
                return [row[0] for row in cur.fetchall()]
        except Exception as exc:
            logger.error("list_tables error: %s", exc)
            return []

    def fetch_data(self, query: str) -> pd.DataFrame:
        """Execute a SQL SELECT and return a DataFrame."""
        if self._conn is None:
            raise RuntimeError("Call connect() before fetch_data().")
        try:
            df = pd.read_sql_query(query, self._conn)
            logger.info("Postgres fetched %d rows.", len(df))
            return df
        except Exception as exc:
            raise RuntimeError(f"Query failed: {exc}") from exc

    def preview(self, table: str, n: int = 5) -> pd.DataFrame:
        return self.fetch_data(f'SELECT * FROM {table} LIMIT {n}')

    def get_columns(self, table: str) -> list[str]:
        try:
            df = self.fetch_data(f"SELECT * FROM {table} LIMIT 0")
            return list(df.columns)
        except Exception:
            return []

    def to_config(self) -> dict:
        """Return serialisable config (password excluded — store via secrets)."""
        cfg = {k: v for k, v in self._config.items() if k != "password"}
        cfg["connector_type"] = "postgres"
        return cfg

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
