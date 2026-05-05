"""
Celery background tasks for the MetricSleuth investigation pipeline.

The worker normalizes the dataset once, persists a prepared parquet artifact,
and fans out downstream work from that canonical object instead of re-reading
the original payload repeatedly.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd
from celery import chord

from api.worker import celery_app
from src.anomaly_detection import detect_anomalies, get_anomaly_dates
from src.contribution_analysis import compute_contributions
from src.correlation_analysis import analyse_correlations
from src.db import save_report_meta, update_analysis_run
from src.hypothesis_engine import generate_hypotheses
from src.llm_summary import generate_executive_summary
from src.prophet_anomaly_detection import ProphetTimeoutError, detect_prophet_anomalies
from src.rag_indexer import index_report
from src.report_generator import build_report, report_to_markdown
from src.segmentation_analysis import analyse_all_segments
from utils.config import ANOMALY_METRICS, MAX_UPLOAD_SIZE_BYTES

logger = logging.getLogger(__name__)

ROW_CAP = 2_000_000
STORAGE_BUCKET = "temp-processing"


def _set_run_status(
    run_id: str,
    user_id: str,
    status: str,
    message: str,
    progress_meta: dict[str, Any] | None = None,
    error_message: str | None = None,
    report_id: str | None = None,
) -> None:
    update_analysis_run(
        job_id=run_id,
        user_id=user_id,
        status=status,
        status_message=message,
        progress_meta=progress_meta,
        error_message=error_message,
        report_id=report_id,
    )


def _download_from_storage(storage_key: str) -> bytes:
    from src.db import get_admin_client
    import httpx

    client = get_admin_client()
    try:
        res = client.storage.from_(STORAGE_BUCKET).create_signed_url(storage_key, 60)
        url = res.get("signedUrl", res.get("signedURL")) if isinstance(res, dict) else res
        if not url:
            raise ValueError("Failed to retrieve signed URL.")
    except Exception as exc:
        raise RuntimeError(f"Could not generate secure download link: {exc}") from exc

    with httpx.Client(follow_redirects=True, timeout=60.0) as hclient:
        with hclient.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_UPLOAD_SIZE_BYTES:
                raise ValueError("Dataset exceeds the maximum allowed size of 200MB.")

            chunks: list[bytes] = []
            bytes_downloaded = 0
            for chunk in response.iter_bytes(chunk_size=8192):
                bytes_downloaded += len(chunk)
                if bytes_downloaded > MAX_UPLOAD_SIZE_BYTES:
                    raise ValueError("Dataset stream exceeds the maximum allowed size of 200MB.")
                chunks.append(chunk)
            return b"".join(chunks)


def _delete_from_storage(storage_key: str) -> None:
    try:
        from src.db import get_admin_client

        client = get_admin_client()
        client.storage.from_(STORAGE_BUCKET).remove([storage_key])
        logger.info("Deleted storage object: %s", storage_key)
    except Exception as exc:
        logger.warning("Failed to delete storage object %s: %s", storage_key, exc)


def _parse_dataframe(file_bytes: bytes, orient: str) -> pd.DataFrame:
    buf = io.BytesIO(file_bytes)
    if orient == "csv":
        df = pd.read_csv(buf, engine="pyarrow", dtype_backend="pyarrow")
    elif orient == "parquet":
        df = pd.read_parquet(buf)
    else:
        df = pd.read_json(buf, orient=orient, dtype_backend="pyarrow")

    if len(df) > ROW_CAP:
        raise ValueError(
            f"Dataset exceeds the maximum allowed size of {ROW_CAP:,} rows "
            f"(received {len(df):,}). Use the staged ingestion workflow for larger payloads."
        )

    float_cols = df.select_dtypes(include=["float64", "Float64", "float64[pyarrow]"]).columns
    if not float_cols.empty:
        try:
            df[float_cols] = df[float_cols].astype("float32[pyarrow]")
        except Exception as exc:
            logger.debug("Float downcast skipped: %s", exc)
    return df


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], utc=True).dt.tz_localize(None)
        normalized = normalized.sort_values("date").reset_index(drop=True)
    return normalized


def _upload_prepared_dataframe(run_id: str, user_id: str, df: pd.DataFrame) -> str:
    from src.db import get_admin_client

    storage_key = f"{user_id}/prepared/{run_id}.parquet"
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    client = get_admin_client()
    client.storage.from_(STORAGE_BUCKET).upload(
        path=storage_key,
        file=buffer.getvalue(),
        file_options={"content-type": "application/octet-stream", "upsert": "true"},
    )
    return storage_key


def _load_prepared_dataframe(storage_key: str) -> pd.DataFrame:
    return _parse_dataframe(_download_from_storage(storage_key), "parquet")


def _load_source_dataframe(storage_key: str | None, dataset_id: str | None, user_id: str, orient: str) -> pd.DataFrame:
    if storage_key:
        file_bytes = _download_from_storage(storage_key)
        df = _parse_dataframe(file_bytes, orient)
        return _normalize_dataframe(df)

    if not dataset_id:
        raise ValueError("dataset_id is required when storage_key is not provided.")

    from src.connectors import load_dataset_from_connector

    df = load_dataset_from_connector(dataset_id, user_id=user_id)
    return _normalize_dataframe(df)


@celery_app.task(bind=True, name="api.tasks.run_rca_pipeline")
def run_rca_pipeline(
    self,
    storage_key: str | None,
    metric: str,
    user_id: str,
    dataset_id: str | None,
    orient: str = "csv",
    api_key: str = "",
    backend: str = "gemini",
    use_prophet: bool = True,
) -> dict[str, Any]:
    run_id = self.request.id or ""
    prepared_storage_key: str | None = None
    try:
        _set_run_status(run_id, user_id, "RUNNING", "Loading dataset from secure storage.", {"stage": "load"})
        df = _load_source_dataframe(storage_key, dataset_id, user_id, orient)

        _set_run_status(run_id, user_id, "RUNNING", "Normalizing and caching a prepared analysis frame.", {"stage": "prepare"})
        prepared_storage_key = _upload_prepared_dataframe(run_id, user_id, df)

        if storage_key:
            _delete_from_storage(storage_key)

        _set_run_status(run_id, user_id, "RUNNING", "Detecting statistical anomalies.", {"stage": "detect"})
        anomalies_df = detect_anomalies(df)
        anomalies_json = anomalies_df.to_json(orient="records", date_format="iso") if not anomalies_df.empty else "[]"

        metrics_to_scan = [candidate for candidate in ANOMALY_METRICS if candidate in df.columns]
        if use_prophet and metrics_to_scan:
            _set_run_status(
                run_id,
                user_id,
                "RUNNING",
                "Prepared frame cached. Fanning out Prophet validation.",
                {"stage": "prophet_fanout", "metrics": metrics_to_scan},
            )
            header = [
                prophet_evaluate_metric.s(
                    prepared_storage_key=prepared_storage_key,
                    scan_metric=scan_metric,
                )
                for scan_metric in metrics_to_scan
            ]
            callback = run_rca_pipeline_callback.s(
                run_id=run_id,
                anomalies_json=anomalies_json,
                prepared_storage_key=prepared_storage_key,
                metric=metric,
                user_id=user_id,
                dataset_id=dataset_id,
                api_key=api_key,
                backend=backend,
            )
            chord(header)(callback)
            return {"status": "processing", "message": "Prophet validation running."}

        run_rca_pipeline_callback.delay(
            [],
            run_id=run_id,
            anomalies_json=anomalies_json,
            prepared_storage_key=prepared_storage_key,
            metric=metric,
            user_id=user_id,
            dataset_id=dataset_id,
            api_key=api_key,
            backend=backend,
        )
        return {"status": "processing", "message": "Deep investigation running."}
    except Exception as exc:
        logger.error("Pipeline launcher crashed for user=%s: %s", user_id, exc, exc_info=True)
        _set_run_status(run_id, user_id, "FAILURE", "The investigation failed before completion.", {"stage": "failed"}, str(exc))
        if storage_key:
            _delete_from_storage(storage_key)
        if prepared_storage_key:
            _delete_from_storage(prepared_storage_key)
        raise


@celery_app.task(bind=True, name="api.tasks.prophet_evaluate_metric")
def prophet_evaluate_metric(
    self,
    prepared_storage_key: str,
    scan_metric: str,
    interval_width: float = 0.95,
) -> str:
    try:
        df = _load_prepared_dataframe(prepared_storage_key)
        if scan_metric not in df.columns:
            return "[]"
        res = detect_prophet_anomalies(df, scan_metric, interval_width)
        return res.to_json(orient="records", date_format="iso") if not res.empty else "[]"
    except ProphetTimeoutError:
        return "[]"
    except Exception as exc:
        logger.warning("Prophet sub-task failed for %s (non-fatal): %s", scan_metric, exc)
        return "[]"


@celery_app.task(bind=True, name="api.tasks.run_rca_pipeline_callback")
def run_rca_pipeline_callback(
    self,
    prophet_results: list[str],
    run_id: str,
    anomalies_json: str,
    prepared_storage_key: str,
    metric: str,
    user_id: str,
    dataset_id: str | None,
    api_key: str,
    backend: str,
) -> dict[str, Any]:
    try:
        _set_run_status(run_id, user_id, "RUNNING", "Aggregating anomaly signals.", {"stage": "aggregate"})

        frames: list[pd.DataFrame] = []
        for res_json in prophet_results:
            if res_json and res_json != "[]":
                frames.append(pd.read_json(io.StringIO(res_json), orient="records"))

        if frames:
            prophet_df = pd.concat(frames, ignore_index=True)
            prophet_df["date"] = pd.to_datetime(prophet_df["date"], utc=True).dt.tz_localize(None)
        else:
            prophet_df = pd.DataFrame()

        anomalies_df = pd.read_json(io.StringIO(anomalies_json), orient="records") if anomalies_json else pd.DataFrame()
        if not anomalies_df.empty and "date" in anomalies_df.columns:
            anomalies_df["date"] = pd.to_datetime(anomalies_df["date"], utc=True).dt.tz_localize(None)

        if not prophet_df.empty:
            prophet_anomaly_dates = set(prophet_df[prophet_df["is_anomaly"]]["date"].tolist())
            zscore_dates = set(anomalies_df["date"].tolist()) if not anomalies_df.empty else set()
            all_anomaly_dates = zscore_dates | prophet_anomaly_dates
            if anomalies_df.empty and prophet_anomaly_dates:
                anomalies_df = (
                    prophet_df[prophet_df["is_anomaly"]]
                    .rename(columns={"deviation": "deviation_score"})
                    .assign(z_score=0.0)
                    .loc[:, ["date", "metric", "observed_value", "expected_value", "z_score", "deviation_score", "direction"]]
                    .reset_index(drop=True)
                )
            elif not anomalies_df.empty:
                anomalies_df = anomalies_df[anomalies_df["date"].isin(all_anomaly_dates)].reset_index(drop=True)

        a_dates = get_anomaly_dates(anomalies_df)
        if not a_dates:
            _set_run_status(
                run_id,
                user_id,
                "SUCCESS",
                "Investigation completed. No material anomalies were detected.",
                {"stage": "complete", "anomalies_detected": 0},
            )
            return {"status": "success", "message": "No anomalies detected."}

        report_date = a_dates[0]
        anom_day = anomalies_df[anomalies_df["date"] == report_date]

        _set_run_status(run_id, user_id, "RUNNING", "Running segmentation, correlation, and contribution analysis.", {"stage": "deep_analysis"})
        df = _load_prepared_dataframe(prepared_storage_key)

        seg_r = analyse_all_segments(df, report_date, metric)
        contrib_df = compute_contributions(df, report_date, primary_metric=metric)
        corr_df = analyse_correlations(df)

        _set_run_status(run_id, user_id, "RUNNING", "Ranking likely drivers and generating a concise brief.", {"stage": "summarize"})
        hyps = generate_hypotheses(contrib_df, seg_r, corr_df, anomalies_df=anomalies_df)
        report_dict = build_report(
            anom_day,
            corr_df,
            seg_r,
            contrib_df,
            hyps,
            report_date,
            primary_metric=metric,
        )

        exec_summary = generate_executive_summary(report_dict, api_key=api_key or None, backend=backend)
        report_md = report_to_markdown(report_dict)

        _set_run_status(run_id, user_id, "RUNNING", "Persisting the investigation report.", {"stage": "persist"})
        top_hyp = hyps[0].title if hyps else ""
        top_conf = hyps[0].confidence if hyps else 0.0
        report_id = save_report_meta(
            user_id=user_id,
            dataset_id=dataset_id,
            anomaly_date=str(report_date)[:10],
            primary_metric=metric,
            executive_summary=exec_summary,
            n_anomalies=len(anom_day),
            n_hypotheses=len(hyps),
            top_hypothesis=top_hyp,
            confidence=top_conf,
            report_md=report_md,
            report_payload=report_dict,
            workflow_status="new",
        )
        if not report_id:
            raise RuntimeError("Report persistence failed.")

        try:
            index_report(
                report_dict,
                user_id=user_id,
                executive_summary=exec_summary,
                report_id=report_id,
                api_key=api_key or None,
            )
        except Exception as exc:
            logger.warning("Report saved but semantic indexing skipped for run %s: %s", run_id, exc)

        _set_run_status(
            run_id,
            user_id,
            "SUCCESS",
            "Investigation complete. Brief saved to the incident inbox.",
            {"stage": "complete", "anomalies_detected": len(anom_day)},
            report_id=report_id,
        )
        logger.info("Pipeline completed successfully for user=%s run=%s", user_id, run_id)
        return {"status": "success", "message": "Pipeline completed. Report saved to database.", "report_id": report_id}
    except Exception as exc:
        logger.error("Callback crashed for user=%s run=%s: %s", user_id, run_id, exc, exc_info=True)
        _set_run_status(run_id, user_id, "FAILURE", "The investigation failed during deep analysis.", {"stage": "failed"}, str(exc))
        raise
    finally:
        if prepared_storage_key:
            _delete_from_storage(prepared_storage_key)
