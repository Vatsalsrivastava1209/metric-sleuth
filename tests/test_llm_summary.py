"""
Tests for src/llm_summary.py
==============================
Verifies the security fix: api_key must never leak into os.environ,
and that the fallback path works correctly without any LLM credentials.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.llm_summary import generate_executive_summary, _fallback_summary, _build_prompt


# ── Minimal report fixture ────────────────────────────────────────────────────

MINIMAL_REPORT = {
    "primary_metric": "revenue",
    "anomaly_date":   "2024-01-15",
    "anomaly_summary": [
        {
            "metric":   "revenue",
            "direction": "drop",
            "date":     "2024-01-15",
            "observed": 8000.0,
            "expected": 12000.0,
            "z_score":  -2.8,
        }
    ],
    "contribution_breakdown": [
        {"factor": "traffic", "pct_change": -35.0, "contribution_pct": 70.0},
        {"factor": "conversion_rate", "pct_change": -10.0, "contribution_pct": 30.0},
    ],
    "segment_impact": {
        "region": [{"region": "US-West", "relative_change_pct": -45.0}],
    },
    "hypotheses": [
        {"id": "H-TRAFFIC-DROP", "title": "Traffic Volume Decline", "confidence": 0.82},
    ],
    "recommended_actions": ["Investigate paid-search campaigns."],
}


# ── Security: os.environ must not be mutated ──────────────────────────────────

def test_api_key_never_written_to_environ_on_fallback():
    """Calling generate_executive_summary must not set any LLM key in os.environ."""
    sentinel_key = "METRICSLEUTH_TEST_SENTINEL_12345"
    os.environ.pop(sentinel_key, None)
    os.environ.pop("LLM_API_KEY", None)

    # Call with force_fallback — no LLM, no key
    _ = generate_executive_summary(MINIMAL_REPORT, force_fallback=True)

    assert "LLM_API_KEY" not in os.environ or os.environ.get("LLM_API_KEY", "") == "", (
        "generate_executive_summary must NOT write to os.environ['LLM_API_KEY']"
    )


def test_api_key_never_written_to_environ_when_key_passed():
    """Passing api_key as argument must not pollute os.environ."""
    original_value = os.environ.get("LLM_API_KEY", "__NOT_SET__")
    os.environ.pop("LLM_API_KEY", None)   # ensure it's unset before the call

    # Even with a (fake) api_key, the function must not write to os.environ.
    # It will fail the actual LLM call (bad key) and fall back gracefully.
    # We only care that os.environ is not mutated.
    _ = generate_executive_summary(
        MINIMAL_REPORT,
        api_key="sk-FAKE_KEY_FOR_TESTING",
        backend="openai",
    )

    current = os.environ.get("LLM_API_KEY", "__NOT_SET__")
    # The key written before the call was "__NOT_SET__" (absent), so if it changed
    # to the fake key, that means os.environ was mutated — which is the bug.
    assert current in ("__NOT_SET__", original_value), (
        f"os.environ['LLM_API_KEY'] was mutated to '{current}' — security regression!"
    )


# ── Fallback summary quality ──────────────────────────────────────────────────

def test_fallback_summary_returns_non_empty_string():
    result = generate_executive_summary(MINIMAL_REPORT, force_fallback=True)
    assert isinstance(result, str) and len(result) > 50, (
        "Fallback summary must be a non-trivial string."
    )


def test_fallback_summary_mentions_anomaly_date():
    result = generate_executive_summary(MINIMAL_REPORT, force_fallback=True)
    assert "2024-01-15" in result, "Fallback summary must include the anomaly date."


def test_fallback_summary_mentions_metric():
    result = generate_executive_summary(MINIMAL_REPORT, force_fallback=True)
    assert "revenue" in result.lower(), "Fallback summary must mention the primary metric."


def test_fallback_summary_on_empty_report():
    """_fallback_summary must not crash on a completely empty report dict."""
    result = _fallback_summary({})
    assert isinstance(result, str) and len(result) > 0


# ── Prompt builder ────────────────────────────────────────────────────────────

def test_build_prompt_contains_metric_and_date():
    prompt = _build_prompt(MINIMAL_REPORT)
    assert "revenue" in prompt
    assert "2024-01-15" in prompt


def test_build_prompt_contains_hypothesis():
    prompt = _build_prompt(MINIMAL_REPORT)
    assert "Traffic Volume Decline" in prompt


# ── No-key behaviour ──────────────────────────────────────────────────────────

def test_no_api_key_uses_fallback():
    """When api_key is None and global LLM_API_KEY is empty, must use fallback."""
    from src import llm_summary as _mod
    original = _mod.LLM_API_KEY
    _mod.LLM_API_KEY = ""   # ensure global key is empty

    try:
        result = generate_executive_summary(MINIMAL_REPORT, api_key=None)
        assert isinstance(result, str) and len(result) > 0
    finally:
        _mod.LLM_API_KEY = original   # restore
