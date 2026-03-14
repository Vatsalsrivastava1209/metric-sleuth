"""
rag_indexer.py
==============
Indexes historical RCA reports into a ChromaDB vector store so they can
be retrieved later by semantic similarity.

How it works
------------
1. Each RCA report (produced by ``report_generator.build_report``) is
   converted to a plain-text document.
2. The document is embedded using a local ``sentence-transformers`` model
   (no API key required).
3. The embedding + metadata are stored in a persistent ChromaDB collection.

The index is stored on disk at ``data/rag_index/`` by default and is
automatically created on first run.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default paths ─────────────────────────────────────────────────────────────
_DEFAULT_INDEX_DIR  = Path("data/rag_index")
_COLLECTION_NAME    = "rca_reports"
_EMBED_MODEL        = "all-MiniLM-L6-v2"   # fast, small, good quality


def _import_deps():
    """Lazy-import chromadb and sentence_transformers."""
    try:
        import chromadb                                       # type: ignore
        from chromadb.utils import embedding_functions as ef  # type: ignore
        return chromadb, ef
    except ImportError as exc:
        raise ImportError(
            "chromadb is not installed. Run: pip install chromadb sentence-transformers"
        ) from exc


def get_collection(index_dir: str | Path = _DEFAULT_INDEX_DIR):
    """Return (or create) the persistent ChromaDB collection.

    Parameters
    ----------
    index_dir:
        Directory where ChromaDB persists its data.

    Returns
    -------
    chromadb.Collection
    """
    chromadb, ef = _import_deps()
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(index_dir))
    embedding_fn = ef.SentenceTransformerEmbeddingFunction(
        model_name=_EMBED_MODEL
    )
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def _report_to_text(report: dict[str, Any]) -> str:
    """Flatten a structured RCA report dict into a single indexable text blob."""
    parts: list[str] = []

    parts.append(f"Anomaly date: {report.get('anomaly_date', 'N/A')}")
    parts.append(f"Primary metric: {report.get('primary_metric', 'N/A')}")

    for a in report.get("anomaly_summary", []):
        parts.append(
            f"Anomaly — {a['metric']} {a['direction']} on {a['date']}: "
            f"observed {a['observed']:.2f} vs expected {a['expected']:.2f} "
            f"(z-score {a['z_score']:.2f})"
        )

    for c in report.get("contribution_breakdown", []):
        parts.append(
            f"Factor {c['factor']} changed {c['pct_change']:.1f}%, "
            f"contributing {c['contribution_pct']:.1f}% of the drop."
        )

    for dim, records in report.get("segment_impact", {}).items():
        if records:
            top = records[0]
            parts.append(
                f"Worst {dim} segment: '{top.get(dim, '?')}' "
                f"({top.get('relative_change_pct', 0):.1f}% vs baseline)"
            )

    for h in report.get("hypotheses", []):
        parts.append(f"Hypothesis [{h['id']}]: {h['title']} — {h['description']}")

    for action in report.get("recommended_actions", []):
        parts.append(f"Action: {action}")

    return "\n".join(parts)


def _report_id(report: dict[str, Any]) -> str:
    """Generate a stable unique ID for a report based on its content hash."""
    key = f"{report.get('anomaly_date', '')}_{report.get('primary_metric', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def index_report(
    report: dict[str, Any],
    executive_summary: str = "",
    index_dir: str | Path = _DEFAULT_INDEX_DIR,
) -> str:
    """Add a single RCA report to the vector index.

    Parameters
    ----------
    report:
        Structured report dict from :func:`report_generator.build_report`.
    executive_summary:
        Plain-text summary to enrich the indexed document.
    index_dir:
        ChromaDB persistence directory.

    Returns
    -------
    str
        The document ID assigned to this report.
    """
    collection = get_collection(index_dir)

    doc_id   = _report_id(report)
    doc_text = _report_to_text(report)
    if executive_summary:
        doc_text = executive_summary + "\n\n" + doc_text

    metadata = {
        "anomaly_date":   str(report.get("anomaly_date", "")),
        "primary_metric": str(report.get("primary_metric", "")),
        "generated_at":   str(report.get("generated_at", "")),
        "n_hypotheses":   len(report.get("hypotheses", [])),
    }

    # Upsert — if the same report (same ID) is re-indexed it replaces the old copy
    collection.upsert(
        ids=[doc_id],
        documents=[doc_text],
        metadatas=[metadata],
    )

    logger.info("Indexed report '%s' (date=%s).", doc_id, metadata["anomaly_date"])
    return doc_id


def index_reports_bulk(
    reports: list[tuple[dict[str, Any], str]],
    index_dir: str | Path = _DEFAULT_INDEX_DIR,
) -> list[str]:
    """Index multiple reports at once.

    Parameters
    ----------
    reports:
        List of ``(report_dict, executive_summary)`` tuples.
    index_dir:
        ChromaDB persistence directory.

    Returns
    -------
    list[str]
        List of assigned document IDs.
    """
    return [index_report(r, s, index_dir) for r, s in reports]


def list_indexed_reports(
    index_dir: str | Path = _DEFAULT_INDEX_DIR,
) -> list[dict]:
    """Return metadata for all indexed reports.

    Returns
    -------
    list[dict]
        Each dict has ``id``, ``anomaly_date``, ``primary_metric``,
        ``generated_at``, ``n_hypotheses``.
    """
    collection = get_collection(index_dir)
    result = collection.get(include=["metadatas"])
    rows = []
    for doc_id, meta in zip(result["ids"], result["metadatas"]):
        rows.append({"id": doc_id, **meta})
    return rows


def clear_index(index_dir: str | Path = _DEFAULT_INDEX_DIR) -> None:
    """Delete all documents from the collection (irreversible)."""
    collection = get_collection(index_dir)
    all_ids = collection.get()["ids"]
    if all_ids:
        collection.delete(ids=all_ids)
    logger.info("Index cleared (%d documents removed).", len(all_ids))


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib, logging
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies, get_anomaly_dates
    from src.segmentation_analysis import analyse_all_segments
    from src.correlation_analysis import analyse_correlations
    from src.contribution_analysis import compute_contributions
    from src.hypothesis_engine import generate_hypotheses
    from src.report_generator import build_report

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    dates = get_anomaly_dates(anomalies)

    for d in dates:
        segs    = analyse_all_segments(raw, d, "revenue")
        contrib = compute_contributions(raw, d)
        corr    = analyse_correlations(raw)
        hyps    = generate_hypotheses(contrib, segs, corr)
        anom_d  = anomalies[anomalies["date"] == d]
        report  = build_report(anom_d, corr, segs, contrib, hyps, d)
        doc_id  = index_report(report)
        print(f"Indexed: {doc_id} (date={d})")

    print("\nAll indexed reports:")
    for r in list_indexed_reports():
        print(" ", r)
