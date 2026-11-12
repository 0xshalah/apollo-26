@echo off
rem Runs pytest from the repo root and writes output + exit code to telemetry\state\last-pytest.txt
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short %* > telemetry\state\last-pytest.txt 2>&1
echo PYTEST_EXIT=%ERRORLEVEL% >> telemetry\state\last-pytest.txt
