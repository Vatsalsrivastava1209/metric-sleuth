"""
scaffold_connector.py
=====================
Base class for connectors that have a defined contract but are not yet live.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class ScaffoldConnector:
    """Connector contract for integrations that are planned but not yet activated."""

    CONNECTOR_TYPE = "scaffold"
    DISPLAY_NAME = "Scaffolded Connector"
    STATUS_NOTE = "Connector scaffolded but not yet wired to a live provider."

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def connect(self, **kwargs: Any) -> tuple[bool, str]:
        self._config = dict(kwargs)
        return False, self.STATUS_NOTE

    def test_connection(self) -> tuple[bool, str]:
        return False, self.STATUS_NOTE

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        raise RuntimeError(self.STATUS_NOTE)

    def preview(self, n: int = 5) -> pd.DataFrame:
        del n
        return pd.DataFrame()

    def get_columns(self) -> list[str]:
        return []

    def to_config(self) -> dict[str, Any]:
        return {"connector_type": self.CONNECTOR_TYPE, "status": "scaffolded", **self._config}
