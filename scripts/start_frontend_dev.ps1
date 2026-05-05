$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$frontendPath = Join-Path $repoRoot "frontend"
$logPath = Join-Path $repoRoot "logs\frontend.live.log"

function Get-RootEnv {
    param([Parameter(Mandatory = $true)][string]$Name)

    $line = Get-Content -Path $envPath |
        Where-Object { $_ -match "^\s*$Name\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return ""
    }

    return (($line -replace "^\s*$Name\s*=\s*", "").Trim())
}

$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_SUPABASE_URL = Get-RootEnv -Name "SUPABASE_URL"
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY = Get-RootEnv -Name "SUPABASE_ANON_KEY"

Set-Location $frontendPath
npm run dev -- --hostname 127.0.0.1 --port 3000 *> $logPath
