"""
mysql_connector.py
==================
MySQL connector using mysql-connector-python.

Install:  pip install mysql-connector-python
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class MySQLConnector:
    """Connector for MySQL / MariaDB databases."""

    CONNECTOR_TYPE = "mysql"
    DISPLAY_NAME   = "MySQL / MariaDB"

    def __init__(self):
        self._conn = None
        self._config: dict[str, Any] = {}

    def connect(
        self,
        host: str,
        port: int = 3306,
        database: str = "",
        user: str = "",
        password: str = "",
        **kwargs,
    ) -> tuple[bool, str]:
        try:
            import mysql.connector  # type: ignore
        except ImportError:
            return False, "mysql-connector-python not installed. Run: pip install mysql-connector-python"

        self._config = dict(host=host, port=port, database=database, user=user, password=password)
        try:
            self._conn = mysql.connector.connect(**self._config)
            logger.info("MySQL connected to %s:%s/%s", host, port, database)
            return True, f"Connected to {database}@{host}:{port}"
        except Exception as exc:
            return False, f"Connection failed: {exc}"

    def test_connection(self) -> tuple[bool, str]:
        if self._conn is None:
            return False, "Not connected."
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
            return True, "Connection is healthy."
        except Exception as exc:
            return False, f"Test failed: {exc}"

    def list_tables(self) -> list[str]:
        if self._conn is None:
            return []
        try:
            cur = self._conn.cursor()
            cur.execute("SHOW TABLES")
            return [row[0] for row in cur.fetchall()]
        except Exception as exc:
            logger.error("list_tables error: %s", exc)
            return []

    def fetch_data(self, query: str) -> pd.DataFrame:
        if self._conn is None:
            raise RuntimeError("Call connect() before fetch_data().")
        try:
            df = pd.read_sql(query, self._conn)
            logger.info("MySQL fetched %d rows.", len(df))
            return df
        except Exception as exc:
            raise RuntimeError(f"Query failed: {exc}") from exc

    def preview(self, table: str, n: int = 5) -> pd.DataFrame:
        return self.fetch_data(f"SELECT * FROM `{table}` LIMIT {n}")

    def get_columns(self, table: str) -> list[str]:
        try:
            df = self.fetch_data(f"SELECT * FROM `{table}` LIMIT 0")
            return list(df.columns)
        except Exception:
            return []

    def to_config(self) -> dict:
        cfg = {k: v for k, v in self._config.items() if k != "password"}
        cfg["connector_type"] = "mysql"
        return cfg

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
