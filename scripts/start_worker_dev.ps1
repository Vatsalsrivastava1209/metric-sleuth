$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$logPath = Join-Path $repoRoot "logs\worker.live.log"

function Get-RootEnv {
    param([Parameter(Mandatory = $true)][string]$Name)

    $line = Get-Content -Path $envPath -ErrorAction SilentlyContinue |
        Where-Object { $_ -match "^\s*$Name\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return ""
    }

    return (($line -replace "^\s*$Name\s*=\s*", "").Trim())
}

$redisUrl = Get-RootEnv -Name "REDIS_URL"
if (-not $redisUrl) {
    $redisUrl = "redis://localhost:6379/0"
}

$env:REDIS_URL = $redisUrl

Set-Location $repoRoot
python -m celery -A api.worker.celery_app worker --pool=solo --loglevel=info *> $logPath
