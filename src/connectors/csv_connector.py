"""
csv_connector.py
================
CSV file connector — wraps the existing MetricSleuth upload logic
into the standard connector interface.
"""

from __future__ import annotations

import io
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class CSVConnector:
    """Connector for CSV / Excel file uploads."""

    CONNECTOR_TYPE = "csv"
    DISPLAY_NAME   = "CSV / Excel Upload"

    def __init__(self):
        self._df: pd.DataFrame | None = None

    # ── Interface ─────────────────────────────────────────────────────────────

    def connect(self, file_obj) -> tuple[bool, str]:
        """
        Load a file-like object (Streamlit UploadedFile or path).

        Returns (success, message).
        """
        try:
            if hasattr(file_obj, "name") and file_obj.name.endswith((".xls", ".xlsx")):
                self._df = pd.read_excel(file_obj)
            else:
                content = file_obj.read() if hasattr(file_obj, "read") else open(file_obj, "rb").read()
                self._df = pd.read_csv(io.BytesIO(content))

            logger.info("CSV connector loaded %d rows, %d columns.", len(self._df), len(self._df.columns))
            return True, f"Loaded {len(self._df):,} rows × {len(self._df.columns)} columns."
        except Exception as exc:
            logger.error("CSV connector error: %s", exc)
            return False, f"Could not read file: {exc}"

    def test_connection(self) -> tuple[bool, str]:
        if self._df is None:
            return False, "No file loaded."
        return True, "File loaded successfully."

    def fetch_data(self, query: str | None = None) -> pd.DataFrame:
        """Return the loaded DataFrame (query param ignored for CSV)."""
        if self._df is None:
            raise RuntimeError("Call connect() before fetch_data().")
        return self._df.copy()

    def preview(self, n: int = 5) -> pd.DataFrame:
        """Return the first n rows for schema mapping preview."""
        if self._df is None:
            return pd.DataFrame()
        return self._df.head(n)

    def get_columns(self) -> list[str]:
        if self._df is None:
            return []
        return list(self._df.columns)

    def row_count(self) -> int:
        if self._df is None:
            return 0
        return len(self._df)

    def to_config(self) -> dict:
        """Return serialisable config (nothing sensitive for CSV)."""
        return {"connector_type": "csv"}
