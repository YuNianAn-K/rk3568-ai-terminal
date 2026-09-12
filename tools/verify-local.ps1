[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$voiceRoot = Join-Path $repoRoot 'apps\voice'

Write-Host '[Windows] Python syntax check'
py -m compileall -q $voiceRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host '[Windows] Deterministic voice tests'
Push-Location $env:TEMP
try {
    & py -m unittest discover -s (Join-Path $voiceRoot 'tests') -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Host '[Windows] Local verification passed'
