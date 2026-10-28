@echo off
setlocal
cd /d "%~dp0"
title SceneTrace - Local Video Workspace

set "SCENETRACE_PY="
set "SCENETRACE_PY_ARGS="

if exist "%~dp0.venv\Scripts\python.exe" set "SCENETRACE_PY=%~dp0.venv\Scripts\python.exe"
if defined SCENETRACE_PY goto launch

if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "SCENETRACE_PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if defined SCENETRACE_PY goto launch

for /d %%P in ("%LocalAppData%\Programs\Python\Python*") do if exist "%%~fP\python.exe" set "SCENETRACE_PY=%%~fP\python.exe"
if defined SCENETRACE_PY goto launch

where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 goto try_python
set "SCENETRACE_PY=py"
set "SCENETRACE_PY_ARGS=-3"
goto launch

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 goto no_python
set "SCENETRACE_PY=python"
goto launch

:launch
"%SCENETRACE_PY%" %SCENETRACE_PY_ARGS% "%~dp0launcher.py" %*
if errorlevel 1 goto failed
exit /b 0

:no_python
echo Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/ and double-click run.bat again.
goto failed

:failed
echo.
echo SceneTrace did not start. Read the message above for the reason.
pause
exit /b 1
