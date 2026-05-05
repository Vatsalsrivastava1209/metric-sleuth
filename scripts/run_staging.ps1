#!/usr/bin/env pwsh
<#
.SYNOPSIS
    MetricSleuth — Staging Environment Launcher & Webhook Stress Tester

.DESCRIPTION
    This script:
      1. Installs required Python packages (httpx, rich, fastapi, uvicorn, stripe)
      2. Starts the mock webhook staging server in the background
      3. Waits for the server to be ready (health check loop)
      4. Runs the full webhook stress test suite against it
      5. Displays the final results table
      6. Optionally queries the /debug/writes endpoint to validate DB state
      7. Gracefully shuts down the staging server

.USAGE
    From the metric-sleuth project root in PowerShell:
        .\scripts\run_staging.ps1

    With custom parameters:
        .\scripts\run_staging.ps1 -Workers 50 -Requests 300 -Port 8001

.PARAMETER Workers
    Number of concurrent HTTP connections during the stress test. Default: 20

.PARAMETER Requests
    Total functional event requests to send. Default: 100

.PARAMETER Port
    Port for the mock staging server. Default: 8000

.PARAMETER KeepServerRunning
    If specified, the staging server is NOT shut down after tests complete.
    Useful for manual Stripe CLI forwarding afterwards.
#>

param(
    [int]$Workers    = 20,
    [int]$Requests   = 100,
    [int]$Port       = 8000,
    [switch]$KeepServerRunning
)

$ErrorActionPreference = "Stop"

$GREEN  = "`e[32m"
$YELLOW = "`e[33m"
$RED    = "`e[31m"
$CYAN   = "`e[36m"
$RESET  = "`e[0m"

function Write-Header([string]$msg) {
    Write-Host ""
    Write-Host "$CYAN══════════════════════════════════════════════════════════$RESET"
    Write-Host "$CYAN  $msg$RESET"
    Write-Host "$CYAN══════════════════════════════════════════════════════════$RESET"
}

function Write-Step([string]$msg) {
    Write-Host "$YELLOW  ▶ $msg$RESET"
}

function Write-OK([string]$msg) {
    Write-Host "$GREEN  ✔ $msg$RESET"
}

function Write-Fail([string]$msg) {
    Write-Host "$RED  ✘ $msg$RESET"
}

# ── Resolve paths ──────────────────────────────────────────────────────────────
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$MockServer  = Join-Path $ScriptDir "mock_webhook_server.py"
$StressTest  = Join-Path $ScriptDir "webhook_stress_test.py"

Write-Header "MetricSleuth Staging Environment & Webhook Stress Tester"
Write-Step "Project root : $ProjectRoot"
Write-Step "Mock server  : $MockServer"
Write-Step "Stress test  : $StressTest"

# ── Step 1: Install Python dependencies ───────────────────────────────────────
Write-Header "Step 1: Installing Python Dependencies"

$pip_packages = @("httpx", "rich", "fastapi", "uvicorn[standard]", "stripe", "python-dotenv")
foreach ($pkg in $pip_packages) {
    Write-Step "Ensuring $pkg is installed..."
    python -m pip install $pkg --quiet --disable-pip-version-check 2>&1 | Out-Null
}
Write-OK "All dependencies satisfied."

# ── Step 2: Start mock staging server ─────────────────────────────────────────
Write-Header "Step 2: Starting Mock Webhook Staging Server (Port $Port)"

$env:STRIPE_WEBHOOK_SECRET = "whsec_test_stress_test_secret_key_1234"
$env:STRIPE_PRICE_PRO       = "price_test_pro_monthly"
$env:STRIPE_PRICE_BUSINESS  = "price_test_business_monthly"
$env:PORT                   = $Port

$ServerProcess = Start-Process `
    -FilePath "python" `
    -ArgumentList "$MockServer" `
    -WorkingDirectory $ProjectRoot `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$env:TEMP\mock_server_stdout.log" `
    -RedirectStandardError  "$env:TEMP\mock_server_stderr.log"

Write-Step "Server PID: $($ServerProcess.Id)"

# ── Step 3: Wait for server health ────────────────────────────────────────────
Write-Header "Step 3: Waiting for Server Readiness"

$BaseUrl     = "http://localhost:$Port"
$HealthUrl   = "$BaseUrl/api/health"
$MaxAttempts = 30
$Attempt     = 0
$Ready       = $false

while ($Attempt -lt $MaxAttempts) {
    Start-Sleep -Milliseconds 500
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200) {
            $Ready = $true
            break
        }
    } catch { }
    $Attempt++
    Write-Host "  Waiting for server... ($Attempt/$MaxAttempts)" -NoNewline
    Write-Host "`r" -NoNewline
}

if (-not $Ready) {
    Write-Fail "Server did not become ready in time."
    Write-Host ""
    Write-Host "Server stderr log:"
    Get-Content "$env:TEMP\mock_server_stderr.log" -ErrorAction SilentlyContinue | Select-Object -Last 20
    $ServerProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-OK "Server is live at $BaseUrl"

# ── Step 4: Run the stress test ───────────────────────────────────────────────
Write-Header "Step 4: Running Webhook Stress Test Suite"

$WebhookUrl = "$BaseUrl/api/v1/webhooks/stripe"

Write-Step "Target URL : $WebhookUrl"
Write-Step "Workers    : $Workers"
Write-Step "Requests   : $Requests"
Write-Host ""

$StressExitCode = 0
try {
    python "$StressTest" `
        --url "$WebhookUrl" `
        --secret "whsec_test_stress_test_secret_key_1234" `
        --workers $Workers `
        --requests $Requests
    $StressExitCode = $LASTEXITCODE
} catch {
    Write-Fail "Stress test runner threw an exception: $_"
    $StressExitCode = 1
}

# ── Step 5: Inspect DB write state ────────────────────────────────────────────
Write-Header "Step 5: Inspecting In-Memory DB State"

try {
    $debugResp = Invoke-WebRequest -Uri "$BaseUrl/api/v1/webhooks/debug/writes" -UseBasicParsing -TimeoutSec 5
    $dbState = $debugResp.Content | ConvertFrom-Json
    Write-OK "Total DB writes recorded: $($dbState.total_writes)"
    Write-Step "Unique customer profiles touched: $($dbState.profile_states.PSObject.Properties.Count)"
    Write-Host ""
    $dbState.profile_states.PSObject.Properties | ForEach-Object {
        Write-Host "  $CYAN$($_.Name)$RESET → $($_.Value | ConvertTo-Json -Compress)"
    }
} catch {
    Write-Fail "Could not fetch debug state: $_"
}

# ── Step 6: Shutdown ──────────────────────────────────────────────────────────
if (-not $KeepServerRunning) {
    Write-Header "Step 6: Shutting Down Staging Server"
    $ServerProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-OK "Server stopped. PID $($ServerProcess.Id) terminated."
} else {
    Write-Header "Step 6: Server Kept Running (--KeepServerRunning)"
    Write-OK "Staging server still running at $BaseUrl (PID $($ServerProcess.Id))"
    Write-Step "Use 'stripe listen --forward-to $WebhookUrl' to forward live Stripe sandbox events."
    Write-Step "Stop it manually: Stop-Process -Id $($ServerProcess.Id)"
}

# ── Final Verdict ─────────────────────────────────────────────────────────────
Write-Host ""
if ($StressExitCode -eq 0) {
    Write-Host "$GREEN╔══════════════════════════════════════════╗$RESET"
    Write-Host "$GREEN║   ✅  ALL WEBHOOK TESTS PASSED            ║$RESET"
    Write-Host "$GREEN╚══════════════════════════════════════════╝$RESET"
} else {
    Write-Host "$RED╔══════════════════════════════════════════╗$RESET"
    Write-Host "$RED║   ❌  SOME WEBHOOK TESTS FAILED           ║$RESET"
    Write-Host "$RED╚══════════════════════════════════════════╝$RESET"
    Write-Host "$YELLOW  Check results above for failing scenarios.$RESET"
}
Write-Host ""

exit $StressExitCode
