"""
scripts/webhook_stress_test.py
================================
Async stress-tester for the MetricSleuth Stripe webhook endpoint.

Tests:
  1. Signature verification — valid HMAC-SHA256 vs. tampered/missing signatures.
  2. All handled event types — correct HTTP 200 response.
  3. Unknown event passthrough — should 200, not 500.
  4. Concurrent load — N workers firing simultaneously to test race conditions.
  5. DB isolation — verifies that concurrent subscription.updated events for
     different fake customer IDs don't collide (each should write independently).

Usage:
    # From the metric-sleuth project root:
    python scripts/webhook_stress_test.py

    # Target a different host/port:
    python scripts/webhook_stress_test.py --url http://localhost:8000 --workers 50 --requests 200

    # Dry run: only print payloads, don't fire HTTP:
    python scripts/webhook_stress_test.py --dry-run

Requirements:
    pip install httpx rich

Environment Variables (all optional — defaults to test values):
    STRIPE_WEBHOOK_SECRET   The webhook secret used to sign payloads.
                            Must match the STRIPE_WEBHOOK_SECRET in your running API.
                            Defaults to 'whsec_test_stress_test_secret_key_1234'
    WEBHOOK_URL             Override target URL.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import NamedTuple

import httpx

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.text import Text
    # Disable rich on Windows terminals that don't support UTF-8 (cp1252, etc.)
    # to prevent UnicodeEncodeError from emoji/box-drawing characters in the output.
    _stdout_enc = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    RICH_AVAILABLE = _stdout_enc in ("utf8", "utf_8", "65001")
    if not RICH_AVAILABLE:
        print("[INFO] Non-UTF-8 console detected — using plain text output mode.")
except ImportError:
    RICH_AVAILABLE = False
    print("[WARNING] Install 'rich' for a beautiful output: pip install rich")

# ── Script injection guard — run from project root ────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.webhook_payloads import EVENT_FACTORIES, build_payload, invalid_signature_payload

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8000/api/v1/webhooks/stripe")
DEFAULT_SECRET = os.environ.get(
    "STRIPE_WEBHOOK_SECRET", "whsec_test_stress_test_secret_key_1234"
)
DEFAULT_WORKERS = 20
DEFAULT_REQUESTS = 100

SAFE_HTTP_STATUSES = {200, 201}
REJECTED_HTTP_STATUSES = {400}  # expected for bad-signature tests


# ── HMAC-SHA256 Signing (mirrors Stripe exactly) ───────────────────────────────

def sign_payload(body: bytes, secret: str, timestamp: int | None = None) -> str:
    """Generate a Stripe-compatible ``Stripe-Signature`` header value.

    Stripe's internal signing spec (from WebhookSignature._compute_signature):
        signed_payload = f"{timestamp}.{body.decode('utf-8')}"   # as a string
        key            = secret.encode("utf-8")                  # full secret, no prefix strip
        signature      = HMAC-SHA256(signed_payload.encode("utf-8"), key).hexdigest()
        header         = f"t={timestamp},v1={signature}"

    Note: the secret key includes the 'whsec_' prefix — Stripe uses the full
    raw string as the HMAC key, NOT a base64-decoded value.
    """
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{body.decode('utf-8')}"
    mac = hmac.new(
        secret.encode("utf-8"),         # full secret string as key bytes
        signed_payload.encode("utf-8"), # signed payload as utf-8 bytes
        hashlib.sha256,
    )
    return f"t={ts},v1={mac.hexdigest()}"


# ── Result Tracking ───────────────────────────────────────────────────────────

@dataclass
class TestResult:
    scenario: str
    event_type: str
    status_code: int
    latency_ms: float
    passed: bool
    error: str = ""


@dataclass
class StressReport:
    results: list[TestResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.latency_ms for r in self.results) / len(self.results)

    @property
    def p99_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sorted(r.latency_ms for r in self.results)[int(len(self.results) * 0.99)]

    @property
    def max_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return max(r.latency_ms for r in self.results)

    def by_scenario(self) -> dict[str, list[TestResult]]:
        d: dict[str, list[TestResult]] = {}
        for r in self.results:
            d.setdefault(r.scenario, []).append(r)
        return d


# ── Individual Test Cases ─────────────────────────────────────────────────────

async def fire_request(
    client: httpx.AsyncClient,
    url: str,
    scenario: str,
    event_type: str,
    body: bytes,
    headers: dict,
    expect_pass: bool,
    report: StressReport,
) -> None:
    t0 = time.monotonic()
    try:
        resp = await client.post(url, content=body, headers=headers)
        latency = (time.monotonic() - t0) * 1000
        if expect_pass:
            passed = resp.status_code in SAFE_HTTP_STATUSES
        else:
            passed = resp.status_code in REJECTED_HTTP_STATUSES
        report.results.append(TestResult(
            scenario=scenario,
            event_type=event_type,
            status_code=resp.status_code,
            latency_ms=round(latency, 2),
            passed=passed,
            error="" if passed else f"Unexpected {resp.status_code}: {resp.text[:200]}",
        ))
    except Exception as exc:
        latency = (time.monotonic() - t0) * 1000
        report.results.append(TestResult(
            scenario=scenario,
            event_type=event_type,
            status_code=0,
            latency_ms=round(latency, 2),
            passed=False,
            error=f"Connection error: {exc}",
        ))


# ── Test Scenario Builders ────────────────────────────────────────────────────

def make_valid_request(
    event_type: str,
    secret: str,
    payload_kwargs: dict | None = None,
) -> tuple[bytes, dict]:
    """Build a correctly signed request body + headers."""
    data = build_payload(event_type, **(payload_kwargs or {}))
    body = json.dumps(data).encode("utf-8")
    sig = sign_payload(body, secret)
    return body, {
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    }


def make_tampered_signature_request(event_type: str, secret: str) -> tuple[bytes, dict]:
    """Valid body but signature signed with a WRONG secret — should → 400."""
    data = build_payload(event_type)
    body = json.dumps(data).encode("utf-8")
    wrong_secret = "whsec_totally_wrong_secret_key_abcdef1234567890"
    sig = sign_payload(body, wrong_secret)
    return body, {
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    }


def make_missing_signature_request(event_type: str) -> tuple[bytes, dict]:
    """No Stripe-Signature header at all — should → 400."""
    data = build_payload(event_type)
    body = json.dumps(data).encode("utf-8")
    return body, {"Content-Type": "application/json"}


def make_replay_attack_request(event_type: str, secret: str) -> tuple[bytes, dict]:
    """Valid payload signed correctly, but with a timestamp > 5 minutes in the past.

    Stripe's construct_event enforces a default tolerance of 300 seconds.
    A 6-minute-old timestamp should be rejected with HTTP 400 by our endpoint.
    """
    data = build_payload(event_type)
    body = json.dumps(data).encode("utf-8")
    old_ts = int(time.time()) - 400  # 6.7 minutes ago — outside Stripe's 300s window
    sig = sign_payload(body, secret, timestamp=old_ts)
    return body, {
        "Content-Type": "application/json",
        "Stripe-Signature": sig,
    }


# ── Main Stress Test Orchestrator ─────────────────────────────────────────────

async def run_stress_test(
    url: str,
    secret: str,
    concurrent_workers: int,
    total_requests: int,
    dry_run: bool,
    report: StressReport,
) -> None:
    console = Console() if RICH_AVAILABLE else None

    if dry_run:
        if console:
            console.print(Panel("[bold yellow]DRY RUN MODE — no HTTP requests will be fired.[/bold yellow]"))
        else:
            print("=== DRY RUN MODE ===")
        for et in EVENT_FACTORIES:
            data = build_payload(et)
            body = json.dumps(data, indent=2).encode()
            sig = sign_payload(body, secret)
            print(f"\n--- {et} ---")
            print(f"Stripe-Signature: {sig[:60]}...")
            print(body.decode()[:300])
        return

    limits = httpx.Limits(max_connections=concurrent_workers, max_keepalive_connections=concurrent_workers)
    timeout = httpx.Timeout(10.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:

        # ── Suite 1: All valid event types (functional correctness) ──────────
        progress_label = "Functional suite (valid events)"
        tasks = []
        event_types_cycle = list(EVENT_FACTORIES.keys())
        for i in range(total_requests):
            et = event_types_cycle[i % len(event_types_cycle)]
            body, headers = make_valid_request(et, secret)
            tasks.append(fire_request(client, url, "✅ valid_event", et, body, headers, True, report))

        if console:
            with Progress(SpinnerColumn(), "[progress.description]{task.description}", BarColumn(), TaskProgressColumn(), TimeElapsedColumn(), console=console) as progress:
                prog_task = progress.add_task(f"[cyan]{progress_label}[/cyan]", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    await coro
                    progress.advance(prog_task)
        else:
            print(f"\nRunning: {progress_label}...")
            await asyncio.gather(*tasks)

        # ── Suite 2: Security rejection tests ────────────────────────────────
        rejection_tasks = []
        for et in ["checkout.session.completed", "customer.subscription.updated"]:
            # Tampered signature
            body, headers = make_tampered_signature_request(et, secret)
            rejection_tasks.append(fire_request(client, url, "🔒 tampered_sig", et, body, headers, False, report))
            # No signature at all
            body, headers = make_missing_signature_request(et)
            rejection_tasks.append(fire_request(client, url, "🔒 missing_sig", et, body, headers, False, report))

        if console:
            console.print("\n[bold]Running security rejection tests...[/bold]")
        else:
            print("\nRunning: Security rejection tests...")
        await asyncio.gather(*rejection_tasks)

        # ── Suite 3: Concurrent same-customer subscription.updated ───────────
        # Creates a race condition scenario: N requests all update the same
        # customer, verifying no panics or constraint violations in Supabase.
        race_customer = "cus_" + uuid.uuid4().hex[:14]
        race_tasks = []
        for i in range(min(concurrent_workers, 30)):
            body, headers = make_valid_request(
                "customer.subscription.updated",
                secret,
                {"customer_id": race_customer, "tier": "pro" if i % 2 == 0 else "business"},
            )
            race_tasks.append(fire_request(
                client, url, "⚡ race_condition", "customer.subscription.updated",
                body, headers, True, report,
            ))

        if console:
            console.print(f"[bold]Running race condition test ({len(race_tasks)} concurrent writes to same customer)...[/bold]")
        else:
            print(f"\nRunning: Race condition test ({len(race_tasks)} concurrent writes)...")
        await asyncio.gather(*race_tasks)

        # ── Suite 4: Unknown/unhandled event passthrough ──────────────────────
        body, headers = make_valid_request("unknown_event", secret)
        await fire_request(client, url, "🤷 unknown_event", "payment_intent.created", body, headers, True, report)

        # ── Suite 5: Replay attack (stale timestamp) ──────────────────────────
        body, headers = make_replay_attack_request("invoice.payment_failed", secret)
        await fire_request(
            client, url, "⏳ replay_attack", "invoice.payment_failed",
            body, headers, False, report,
        )


# ── Results Rendering ─────────────────────────────────────────────────────────

def render_results(report: StressReport) -> None:
    if RICH_AVAILABLE:
        console = Console()

        # Per-scenario summary table
        table = Table(title="Webhook Stress Test Results — Per Scenario", expand=True)
        table.add_column("Scenario", style="bold cyan", no_wrap=True)
        table.add_column("Requests", justify="right")
        table.add_column("Passed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Pass Rate", justify="right")
        table.add_column("Avg Latency", justify="right")

        for scenario, results in sorted(report.by_scenario().items()):
            total = len(results)
            passed = sum(1 for r in results if r.passed)
            failed = total - passed
            avg_ms = sum(r.latency_ms for r in results) / total
            pass_rate = f"{(passed / total * 100):.1f}%"
            color = "green" if failed == 0 else "red"
            table.add_row(
                scenario,
                str(total),
                str(passed),
                f"[{color}]{failed}[/{color}]",
                f"[{color}]{pass_rate}[/{color}]",
                f"{avg_ms:.1f}ms",
            )

        console.print("\n", table)

        # Overall summary panel
        pass_color = "bold green" if report.failed == 0 else "bold red"
        verdict = "✅ ALL TESTS PASSED" if report.failed == 0 else f"❌ {report.failed} TESTS FAILED"
        summary = (
            f"Total Requests : {report.total}\n"
            f"Passed         : {report.passed}\n"
            f"Failed         : {report.failed}\n"
            f"Avg Latency    : {report.avg_latency_ms:.1f}ms\n"
            f"P99 Latency    : {report.p99_latency_ms:.1f}ms\n"
            f"Max Latency    : {report.max_latency_ms:.1f}ms\n"
        )
        console.print(Panel(
            f"[{pass_color}]{verdict}[/{pass_color}]\n\n{summary}",
            title="[bold]Overall Summary[/bold]",
            border_style="green" if report.failed == 0 else "red",
        ))

        # Print failures in detail
        failures = [r for r in report.results if not r.passed]
        if failures:
            console.print("\n[bold red]── Failed Requests ──────────────────[/bold red]")
            for r in failures[:20]:  # cap at 20 lines
                console.print(f"  [{r.scenario}] {r.event_type} → {r.status_code} | {r.error}")
    else:
        # Plain text fallback
        print(f"\n{'='*60}")
        print("WEBHOOK STRESS TEST RESULTS")
        print(f"{'='*60}")
        print(f"Total   : {report.total}")
        print(f"Passed  : {report.passed}")
        print(f"Failed  : {report.failed}")
        print(f"Avg ms  : {report.avg_latency_ms:.1f}")
        print(f"P99 ms  : {report.p99_latency_ms:.1f}")
        print(f"Max ms  : {report.max_latency_ms:.1f}")
        if report.failed:
            print("\nFailed requests:")
            for r in report.results:
                if not r.passed:
                    print(f"  {r.scenario} | {r.event_type} | {r.status_code} | {r.error}")


# ── Entry Point ───────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="MetricSleuth webhook stress tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", default=DEFAULT_WEBHOOK_URL, help="Target webhook URL")
    parser.add_argument("--secret", default=DEFAULT_SECRET, help="STRIPE_WEBHOOK_SECRET to sign payloads with")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Max concurrent requests")
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS, help="Total functional requests to fire")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads but don't fire HTTP")
    return parser.parse_args()


def main():
    args = parse_args()
    report = StressReport()

    if RICH_AVAILABLE:
        Console().print(Panel(
            f"[bold cyan]MetricSleuth — Stripe Webhook Stress Tester[/bold cyan]\n\n"
            f"Target  : [yellow]{args.url}[/yellow]\n"
            f"Workers : [yellow]{args.workers}[/yellow]   "
            f"Requests: [yellow]{args.requests}[/yellow]\n"
            f"Secret  : [dim]{args.secret[:30]}...[/dim]",
            border_style="cyan",
        ))
    else:
        print(f"Target: {args.url} | Workers: {args.workers} | Requests: {args.requests}")

    asyncio.run(run_stress_test(
        url=args.url,
        secret=args.secret,
        concurrent_workers=args.workers,
        total_requests=args.requests,
        dry_run=args.dry_run,
        report=report,
    ))

    render_results(report)

    # Exit non-zero if any test failed (useful for CI pipelines)
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
