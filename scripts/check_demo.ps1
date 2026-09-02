param(
    [string]$Destination = "workspace/demo",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = [System.IO.Path]::GetFullPath((Join-Path $repository $Destination))
$failures = [System.Collections.Generic.List[string]]::new()

if (-not $env:OPENAI_API_KEY) { $failures.Add("OPENAI_API_KEY is not configured") }
if (-not $env:OPENAI_MODEL) { $failures.Add("OPENAI_MODEL is not configured") }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $failures.Add("python is unavailable") }
if (-not (Test-Path -LiteralPath (Join-Path $target "pricing.py"))) {
    $failures.Add("demo workspace is missing; run scripts\prepare_demo.ps1")
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) { $failures.Add("port $Port is already in use") }

if (Test-Path -LiteralPath (Join-Path $target ".git")) {
    $changes = git -C $target status --porcelain
    if ($changes) { $failures.Add("demo workspace has uncommitted changes; prepare it again") }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Host "[FAIL] $_" -ForegroundColor Red }
    exit 1
}

Write-Host "[OK] Demo workspace, API configuration, Python, Git state, and port are ready."
Write-Host "Launch: trace-agent --workspace `"$target`" --memory full"
