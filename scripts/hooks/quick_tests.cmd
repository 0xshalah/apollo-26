@echo off
rem Kiro hook command: fast Python suite (not slow). Prints the summary and exits with pytest's code.
rem Skipped while a Flight Watch session is live (telemetry\FLIGHT_MODE present).
cd /d "%~dp0..\.."
if exist "telemetry\FLIGHT_MODE" (
  echo Apollo-26: Flight Watch is live; quick tests skipped.
  exit /b 0
)
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short -m "not slow" > telemetry\state\hook-pytest.txt 2>&1
set "CODE=%ERRORLEVEL%"
type telemetry\state\hook-pytest.txt
echo PYTEST_EXIT=%CODE%
exit /b %CODE%
