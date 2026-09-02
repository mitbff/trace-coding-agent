param(
    [string]$Destination = "workspace/demo"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = [System.IO.Path]::GetFullPath((Join-Path $repository "workspace"))
$target = [System.IO.Path]::GetFullPath((Join-Path $repository $Destination))
$workspacePrefix = $workspaceRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $target.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Demo destination must stay inside $workspaceRoot"
}
if ($target -eq $workspaceRoot) {
    throw "Refusing to replace the workspace root"
}

$source = Join-Path $repository "examples\order_demo"
if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
New-Item -ItemType Directory -Path $target | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
Copy-Item -LiteralPath (Join-Path $source ".gitignore") -Destination $target -Force

git -C $target init --quiet
git -C $target add .
git -C $target -c user.name="Trace Agent Demo" -c user.email="demo@local" commit --quiet -m "demo: initial faulty implementation"

Push-Location $target
try {
    python -m pytest -q pricing_check.py order_check.py
    $testExit = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($testExit -ne 1) {
    throw "Expected the initial demo tests to fail with exit code 1, got $testExit"
}

Write-Host "Demo workspace prepared: $target"
Write-Host "Initial state confirmed: the intended tests fail."
Write-Host "Start with: trace-agent --workspace `"$target`" --memory full"
Write-Host "Then choose terminal chat or Web UI."
exit 0
