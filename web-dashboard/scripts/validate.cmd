@echo off
rem Frontend validation chain (tech.md): lint, typecheck, tests, build, export check. Output: logs\validate.log
setlocal
cd /d "%~dp0.."
set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
if not exist logs mkdir logs
set "OUT=logs\validate.log"
echo === lint > "%OUT%"
call npm run lint >> "%OUT%" 2>&1
echo LINT_EXIT=%ERRORLEVEL% >> "%OUT%"
echo === typecheck >> "%OUT%"
call npm run typecheck >> "%OUT%" 2>&1
echo TYPECHECK_EXIT=%ERRORLEVEL% >> "%OUT%"
echo === test >> "%OUT%"
call npm test -- --run >> "%OUT%" 2>&1
echo TEST_EXIT=%ERRORLEVEL% >> "%OUT%"
echo === build >> "%OUT%"
call npm run build >> "%OUT%" 2>&1
echo BUILD_EXIT=%ERRORLEVEL% >> "%OUT%"
echo === verify:export >> "%OUT%"
call npm run verify:export >> "%OUT%" 2>&1
echo VERIFY_EXIT=%ERRORLEVEL% >> "%OUT%"
echo VALIDATE_DONE >> "%OUT%"
endlocal
