# Runs the Python test suite and prints a compact summary.
# Usage: powershell -File scripts\test.ps1 [-Full] [-- extra pytest args]
param(
    [switch]$Full,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root 'telemetry\state\last-pytest.txt'
$markerArgs = @()
if ($Full) { $env:HYPOTHESIS_PROFILE = 'full' } else { $markerArgs = @('-m', 'not slow') }
Push-Location $root
try {
    & $python -m pytest -q -p no:cacheprovider --tb=short @markerArgs @PytestArgs *> $log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
Get-Content $log | Select-Object -Last 60
Write-Output "PYTEST_EXIT=$code"
exit $code
