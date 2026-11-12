@echo off
rem Clean-room CLI smoke test: build sample WAV, provision a scratch telemetry dir, decode the WAV.
rem Output: telemetry\state\smoke-cli.txt
cd /d "%~dp0.."
set "OUT=telemetry\state\smoke-cli.txt"
set "SCRATCH=%TEMP%\apollo26-smoke"
if exist "%SCRATCH%" rmdir /s /q "%SCRATCH%"
set APOLLO26_LINK_KEY=apollo26-link-demo-key-v1
set APOLLO26_OPERATOR_KEY=apollo26-operator-demo-key-v1
echo === make_sample_wav > "%OUT%"
.venv\Scripts\python.exe scripts\make_sample_wav.py >> "%OUT%" 2>&1
echo exit=%ERRORLEVEL% >> "%OUT%"
echo === provision >> "%OUT%"
.venv\Scripts\python.exe -m acoustic.daemon --telemetry-dir "%SCRATCH%" --provision-sequence 0 >> "%OUT%" 2>&1
echo exit=%ERRORLEVEL% >> "%OUT%"
echo === decode >> "%OUT%"
.venv\Scripts\python.exe -m acoustic.daemon --telemetry-dir "%SCRATCH%" --env-file NUL --input web-dashboard\public\sample_burst.wav >> "%OUT%" 2>&1
echo exit=%ERRORLEVEL% >> "%OUT%"
echo === replay same WAV (must be rejected REPLAY) >> "%OUT%"
.venv\Scripts\python.exe -m acoustic.daemon --telemetry-dir "%SCRATCH%" --env-file NUL --input web-dashboard\public\sample_burst.wav >> "%OUT%" 2>&1
echo exit=%ERRORLEVEL% >> "%OUT%"
echo === inbox >> "%OUT%"
dir /b "%SCRATCH%\inbox" >> "%OUT%" 2>&1
echo === rejected >> "%OUT%"
dir /b "%SCRATCH%\rejected" >> "%OUT%" 2>&1
echo SMOKE_DONE >> "%OUT%"
