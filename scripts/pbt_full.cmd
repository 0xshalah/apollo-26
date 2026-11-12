@echo off
rem Full-profile property-based test run (Hypothesis max_examples=10000, fixed seed).
rem Output: telemetry\state\pbt-full.txt (pytest output, durations, exit code, wall time).
setlocal
cd /d "%~dp0.."
set "OUT=telemetry\state\pbt-full.txt"
set HYPOTHESIS_PROFILE=full
echo START=%DATE% %TIME% > "%OUT%"
.venv\Scripts\python.exe -c "import sys, hypothesis, pytest, platform; print('python', sys.version.split()[0], 'hypothesis', hypothesis.__version__, 'pytest', pytest.__version__, platform.platform())" >> "%OUT%" 2>&1
.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rA --durations=25 --hypothesis-seed=2026 --hypothesis-show-statistics --junitxml=telemetry\state\pbt-full.xml >> "%OUT%" 2>&1
echo PYTEST_EXIT=%ERRORLEVEL% >> "%OUT%"
echo END=%DATE% %TIME% >> "%OUT%"
.venv\Scripts\python.exe scripts\write_test_summary.py --junit telemetry\state\pbt-full.xml --profile full --report-path docs/pbt-report.md --out docs\test-summary.json >> "%OUT%" 2>&1
echo SUMMARY_EXIT=%ERRORLEVEL% >> "%OUT%"
.venv\Scripts\python.exe scripts\write_pbt_report.py --log "%OUT%" --junit telemetry\state\pbt-full.xml --out docs\pbt-report.md
echo REPORT_EXIT=%ERRORLEVEL%
endlocal
