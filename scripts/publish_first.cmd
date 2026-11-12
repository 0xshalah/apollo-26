@echo off
rem First commit + public GitHub repo for Apollo-26. Output: telemetry\state\publish.txt
rem Identity is passed per command (-c); global git config is not modified.
setlocal
cd /d "%~dp0.."
set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
set "GH=%LOCALAPPDATA%\Programs\gh\bin\gh.exe"
set "OUT=telemetry\state\publish.txt"
set "ID=-c user.name=0xshalah -c user.email=147135570+0xshalah@users.noreply.github.com"
echo === init > "%OUT%"
if not exist .git "%GIT%" init -b main >> "%OUT%" 2>&1
"%GIT%" add -A >> "%OUT%" 2>&1
echo === kiro ignored? (must be empty) >> "%OUT%"
"%GIT%" check-ignore .kiro >> "%OUT%" 2>&1
echo === staged count >> "%OUT%"
"%GIT%" diff --cached --name-only | find /c /v "" >> "%OUT%"
echo === secret scan (staged) >> "%OUT%"
"%GIT%" grep --cached -n -I -E "gho_[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{20}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}" >> "%OUT%" 2>&1
echo SECRET_SCAN_EXIT=%ERRORLEVEL% (1 means no match) >> "%OUT%"
echo === commit >> "%OUT%"
"%GIT%" %ID% commit -q -m "Apollo-26: acoustic air-gap guidance bridge (initial public commit)" -m "Specs, steering, hooks, contracts, acoustic daemon, AGC subset emulator, MCP Flight Watch server with safety gate, Next.js ground station and mission console, PBT suites." >> "%OUT%" 2>&1
echo COMMIT_EXIT=%ERRORLEVEL% >> "%OUT%"
"%GIT%" log --oneline -1 >> "%OUT%" 2>&1
echo === create repo >> "%OUT%"
"%GH%" repo create 0xshalah/apollo-26 --public --description "Apollo-26: authenticated Bell-202 acoustic command link from a ground station to an AGC-inspired DSKY, orchestrated by a Kiro agent through MCP. Kiroween 2026 - Frankenstein." >> "%OUT%" 2>&1
echo CREATE_EXIT=%ERRORLEVEL% >> "%OUT%"
"%GIT%" remote remove origin >nul 2>&1
"%GIT%" remote add origin https://github.com/0xshalah/apollo-26.git >> "%OUT%" 2>&1
echo === push >> "%OUT%"
"%GIT%" -c credential.helper= -c "credential.helper=!'%GH:\=/%' auth git-credential" push -u origin main >> "%OUT%" 2>&1
echo PUSH_EXIT=%ERRORLEVEL% >> "%OUT%"
echo PUBLISH_DONE >> "%OUT%"
endlocal
