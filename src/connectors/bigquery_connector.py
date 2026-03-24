"""
bigquery_connector.py
=====================
Google BigQuery connector using the official google-cloud-bigquery client.

Install:  pip install google-cloud-bigquery pyarrow
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class BigQueryConnector:
    """Connector for Google BigQuery."""

    CONNECTOR_TYPE = "bigquery"
    DISPLAY_NAME   = "Google BigQuery"

    def __init__(self):
        self._client = None
        self._project_id: str = ""

    def connect(
        self,
        project_id: str,
        credentials_json: str | dict = "",
        **kwargs,
    ) -> tuple[bool, str]:
        """
        Connect using a service account credentials JSON.

        Parameters
        ----------
        project_id : str
            GCP project ID.
        credentials_json : str | dict
            Service account key JSON (as string or dict).
            If empty, falls back to Application Default Credentials (ADC).
        """
        try:
            from google.cloud import bigquery  # type: ignore
            from google.oauth2 import service_account  # type: ignore
        except ImportError:
            return False, (
                "google-cloud-bigquery not installed. "
                "Run: pip install google-cloud-bigquery pyarrow"
            )

        self._project_id = project_id
        try:
            if credentials_json:
                if isinstance(credentials_json, str):
                    creds_dict = json.loads(credentials_json)
                else:
                    creds_dict = credentials_json

                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
                )
                self._client = bigquery.Client(
                    project=project_id, credentials=credentials
                )
            else:
                # Falls back to ADC (works on GCE, Cloud Run, etc.)
                self._client = bigquery.Client(project=project_id)

            logger.info("BigQuery connected to project %s", project_id)
            return True, f"Connected to BigQuery project '{project_id}'"
        except Exception as exc:
            return False, f"BigQuery connection failed: {exc}"

    def test_connection(self) -> tuple[bool, str]:
        if self._client is None:
            return False, "Not connected."
        try:
            list(self._client.list_datasets(max_results=1))
            return True, "Connection is healthy."
        except Exception as exc:
            return False, f"Test failed: {exc}"

    def list_datasets(self) -> list[str]:
        """Return all dataset IDs in the project."""
        if self._client is None:
            return []
        try:
            return [ds.dataset_id for ds in self._client.list_datasets()]
        except Exception as exc:
            logger.error("list_datasets error: %s", exc)
            return []

    def list_tables(self, dataset_id: str) -> list[str]:
        """Return all table names in a given dataset."""
        if self._client is None:
            return []
        try:
            return [t.table_id for t in self._client.list_tables(dataset_id)]
        except Exception as exc:
            logger.error("list_tables error: %s", exc)
            return []

    def fetch_data(self, query: str) -> pd.DataFrame:
        """Execute a BigQuery SQL query and return a DataFrame."""
        if self._client is None:
            raise RuntimeError("Call connect() before fetch_data().")
        try:
            df = self._client.query(query).to_dataframe()
            logger.info("BigQuery fetched %d rows.", len(df))
            return df
        except Exception as exc:
            raise RuntimeError(f"Query failed: {exc}") from exc

    def preview(self, table_ref: str, n: int = 5) -> pd.DataFrame:
        """table_ref should be 'dataset.table' or 'project.dataset.table'."""
        return self.fetch_data(
            f"SELECT * FROM `{self._project_id}.{table_ref}` LIMIT {n}"
        )

    def get_columns(self, table_ref: str) -> list[str]:
        try:
            df = self.fetch_data(
                f"SELECT * FROM `{self._project_id}.{table_ref}` LIMIT 0"
            )
            return list(df.columns)
        except Exception:
            return []

    def to_config(self) -> dict:
        """Return serialisable config (no credentials stored)."""
        return {
            "connector_type": "bigquery",
            "project_id":     self._project_id,
        }
