@echo off
rem Measure daemon processing latency via /loopback (no air channel). Output: telemetry\state\metrics-loopback.txt
cd /d "%~dp0.."
.venv\Scripts\python.exe scripts\measure_metrics.py --mode loopback --frames 20 > telemetry\state\metrics-loopback.txt 2>&1
echo METRICS_EXIT=%ERRORLEVEL% >> telemetry\state\metrics-loopback.txt
