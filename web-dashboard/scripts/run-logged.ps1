# Runs a command with the portable Node.js on PATH and records output + exit code.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-logged.ps1 -Log logs/build.log npm run build
param(
  [Parameter(Mandatory = $true)][string]$Log,
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd
)
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;" + $env:Path
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logPath = Join-Path $root $Log
New-Item -ItemType Directory -Force (Split-Path -Parent $logPath) | Out-Null
$line = $Cmd -join ' '
[System.IO.File]::WriteAllText($logPath, "> $line`r`n")
cmd /c "($line) >> `"$logPath`" 2>&1"
$code = $LASTEXITCODE
[System.IO.File]::AppendAllText($logPath, "`r`nEXIT_CODE=$code`r`n")
exit $code
