@echo off
rem Measure daemon resources and a same-laptop speaker->microphone self-test. Output: telemetry\state\metrics.txt
cd /d "%~dp0.."
.venv\Scripts\python.exe scripts\measure_metrics.py %* > telemetry\state\metrics.txt 2>&1
echo METRICS_EXIT=%ERRORLEVEL% >> telemetry\state\metrics.txt
