"""
data_loader.py
==============
Responsible for reading the raw CSV dataset and performing minimal
sanity-checks so the rest of the pipeline always receives a clean DataFrame.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from utils.config import DATE_COLUMN, REQUIRED_COLUMNS

logger = logging.getLogger(__name__)


def load_data(file_path: str | Path) -> pd.DataFrame:
    """Read a CSV file and return a cleaned, typed DataFrame.

    Steps performed
    ---------------
    1. Read the CSV with ``pandas.read_csv``.
    2. Validate that all required columns are present.
    3. Parse the ``date`` column as ``datetime64``.
    4. Sort rows chronologically.
    5. Drop fully-duplicate rows.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the CSV file (or a file-like object
        accepted by ``pandas.read_csv``).

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame sorted by date with a ``datetime64`` date column.

    Raises
    ------
    FileNotFoundError
        When *file_path* points to a non-existent file.
    ValueError
        When required columns are missing from the CSV.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {file_path}")

    logger.info("Loading dataset from %s", file_path)
    df = pd.read_csv(file_path)

    # ── Column validation ────────────────────────────────────────────────────
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing)}"
        )

    # ── Type coercion ────────────────────────────────────────────────────────
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN])

    # ── Sort & deduplicate ───────────────────────────────────────────────────
    df = df.drop_duplicates()
    df = df.sort_values(DATE_COLUMN).reset_index(drop=True)

    logger.info("Loaded %d rows × %d columns", *df.shape)
    return df


def load_data_from_upload(uploaded_file) -> pd.DataFrame:
    """Convenience wrapper for Streamlit ``UploadedFile`` objects.

    Parameters
    ----------
    uploaded_file:
        A ``streamlit.runtime.uploaded_file_manager.UploadedFile`` instance.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame (see :func:`load_data` for details).
    """
    df = pd.read_csv(uploaded_file)

    # ── Column validation ────────────────────────────────────────────────────
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"Uploaded file is missing required columns: {sorted(missing)}"
        )

    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN])
    df = df.drop_duplicates()
    df = df.sort_values(DATE_COLUMN).reset_index(drop=True)
    return df


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = load_data("data/sample_ecommerce.csv")
    print(sample.head())
    print(sample.dtypes)
