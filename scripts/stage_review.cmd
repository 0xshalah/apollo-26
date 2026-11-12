@echo off
rem Stage everything and write a pre-publication review to telemetry\state\stage-review.txt (no commit, no network).
setlocal
cd /d "%~dp0.."
set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
set "OUT=telemetry\state\stage-review.txt"
if not exist .git "%GIT%" init -b main > "%OUT%" 2>&1
"%GIT%" add -A >> "%OUT%" 2>&1
echo === kiro ignored? (must be empty) >> "%OUT%"
"%GIT%" check-ignore .kiro .kiro/settings/mcp.json >> "%OUT%" 2>&1
echo === secret scan >> "%OUT%"
"%GIT%" grep --cached -n -I -E "gho_[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{20}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}" >> "%OUT%" 2>&1
echo SECRET_SCAN_EXIT=%ERRORLEVEL% (1 = no match) >> "%OUT%"
echo === largest staged files >> "%OUT%"
"%GIT%" ls-files -s --cached > "%TEMP%\a26-ls.txt"
powershell -NoProfile -Command "git_files=$null; $f = & '%GIT%' ls-files; $f | ForEach-Object { $i = Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue; if ($i) { [pscustomobject]@{KB=[math]::Round($i.Length/1KB,1); Path=$_} } } | Sort-Object KB -Descending | Select-Object -First 12 | Format-Table -AutoSize | Out-String -Width 200" >> "%OUT%" 2>&1
echo === top-level staged paths >> "%OUT%"
powershell -NoProfile -Command "& '%GIT%' ls-files | ForEach-Object { ($_ -split '/')[0] } | Group-Object | Sort-Object Name | Format-Table Count,Name -AutoSize | Out-String" >> "%OUT%" 2>&1
echo REVIEW_DONE >> "%OUT%"
endlocal
