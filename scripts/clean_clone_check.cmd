@echo off
rem TASK 6.4: follow the README quick start in a fresh clone (no Node.js, no microphone).
rem Usage: scripts\clean_clone_check.cmd [repo-url-or-path]   Output: telemetry\state\clean-clone.txt
setlocal
cd /d "%~dp0.."
set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
set "SRC=%~1"
if "%SRC%"=="" set "SRC=https://github.com/0xshalah/apollo-26.git"
set "OUT=%CD%\telemetry\state\clean-clone.txt"
set "DEST=%TEMP%\apollo26-clean-%RANDOM%"
echo SOURCE=%SRC% > "%OUT%"
echo DEST=%DEST% >> "%OUT%"
echo START=%DATE% %TIME% >> "%OUT%"
"%GIT%" clone --depth 1 "%SRC%" "%DEST%" >> "%OUT%" 2>&1 || goto :fail
cd /d "%DEST%"
echo === venv + install >> "%OUT%"
set "PY=python"
where python >nul 2>&1 || set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
echo PYTHON=%PY% >> "%OUT%"
"%PY%" -m venv .venv >> "%OUT%" 2>&1 || goto :fail
.venv\Scripts\python -m pip install --disable-pip-version-check -q -e ".[dev]" >> "%OUT%" 2>&1 || goto :fail
copy .env.example .env >> "%OUT%" 2>&1 || goto :fail
echo === provision >> "%OUT%"
.venv\Scripts\python -m acoustic.daemon --provision-sequence 0 >> "%OUT%" 2>&1 || goto :fail
echo === WAV input (one-shot) >> "%OUT%"
.venv\Scripts\python -m acoustic.daemon --input web-dashboard\public\sample_burst.wav >> "%OUT%" 2>&1 || goto :fail
echo === replay must be rejected >> "%OUT%"
.venv\Scripts\python -m acoustic.daemon --input web-dashboard\public\sample_burst.wav >> "%OUT%" 2>&1
echo === static console present >> "%OUT%"
if exist web-dashboard\out\console\index.html (echo console index.html present >> "%OUT%") else (echo console index.html MISSING >> "%OUT%" & goto :fail)
echo === fast tests >> "%OUT%"
.venv\Scripts\python -m pytest -q -p no:cacheprovider -m "not slow" >> "%OUT%" 2>&1
echo PYTEST_EXIT=%ERRORLEVEL% >> "%OUT%"
echo CLEAN_CLONE=PASS >> "%OUT%"
goto :end
:fail
echo CLEAN_CLONE=FAIL at step above >> "%OUT%"
:end
echo END=%DATE% %TIME% >> "%OUT%"
endlocal
