@echo off
rem Build the static site with basePath=/apollo-26 and publish it to the gh-pages branch.
rem The daemon-hosted build in web-dashboard\out (basePath "") is set aside and restored unchanged.
rem Output: telemetry\state\deploy-pages.txt
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
set "GH=%LOCALAPPDATA%\Programs\gh\bin\gh.exe"
set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
set "OUT=%ROOT%\telemetry\state\deploy-pages.txt"
set "SITE=%TEMP%\apollo26-pages-%RANDOM%"
set "ID=-c user.name=0xshalah -c user.email=147135570+0xshalah@users.noreply.github.com"
echo START=%DATE% %TIME% > "%OUT%"
if exist web-dashboard\out.daemon (echo ABORT: web-dashboard\out.daemon already exists >> "%OUT%" & goto :end)
move web-dashboard\out web-dashboard\out.daemon >> "%OUT%" 2>&1 || goto :end
cd web-dashboard
set "NEXT_PUBLIC_BASE_PATH=/apollo-26"
call npm run build >> "%OUT%" 2>&1
set "BUILD=%ERRORLEVEL%"
set "NEXT_PUBLIC_BASE_PATH="
echo BUILD_EXIT=%BUILD% >> "%OUT%"
if "%BUILD%"=="0" move out "%SITE%" >> "%OUT%" 2>&1
if exist out rmdir /s /q out
move out.daemon out >> "%OUT%" 2>&1
echo RESTORED_DAEMON_OUT=%ERRORLEVEL% >> "%OUT%"
cd /d "%ROOT%"
if not "%BUILD%"=="0" goto :end
type nul > "%SITE%\.nojekyll"
cd /d "%SITE%"
"%GIT%" init -q -b gh-pages >> "%OUT%" 2>&1
"%GIT%" add -A >> "%OUT%" 2>&1
"%GIT%" %ID% commit -q -m "Deploy static ground station and console (basePath /apollo-26)" >> "%OUT%" 2>&1
echo COMMIT_EXIT=%ERRORLEVEL% >> "%OUT%"
"%GIT%" -c credential.helper= -c "credential.helper=!'%GH:\=/%' auth git-credential" push -f https://github.com/0xshalah/apollo-26.git gh-pages >> "%OUT%" 2>&1
echo PUSH_EXIT=%ERRORLEVEL% >> "%OUT%"
cd /d "%ROOT%"
"%GH%" api -X PUT repos/0xshalah/apollo-26/pages -f build_type=legacy -f "source[branch]=gh-pages" -f "source[path]=/" >> "%OUT%" 2>&1
echo PAGES_CONFIG_EXIT=%ERRORLEVEL% >> "%OUT%"
echo === daemon out unchanged? (empty = unchanged) >> "%OUT%"
"%GIT%" status --short web-dashboard/out >> "%OUT%" 2>&1
:end
echo DEPLOY_DONE >> "%OUT%"
endlocal
