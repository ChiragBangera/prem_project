@echo off
rem Prem Lab launcher for Windows: double-click it (or the shortcut that tools\make-windows-shortcut.ps1 puts on your Desktop) to start the app
rem and open it in your browser. The app runs in this window: press Ctrl+C or close the window to stop it. If Prem Lab is already running on
rem this port, this only opens it.
rem
rem   PREM_PORT=8011   another port (default 8010)        PREM_NO_OPEN=1   do not open a browser
rem   anything after the file name goes to "prem serve", for example:  tools\prem-lab.bat --demo
rem   PREM_NO_UPDATE=1 does not look for an update first

rem PREM_LAUNCHER_UPDATED is set when this launcher restarts itself after an update (below). One line, so it is read before it is cleared:
rem cleared for good, kept for this run only, so it never outlives this run
set "PREM_LAUNCHER_UPDATED=" & setlocal & set "PREM_JUST_UPDATED=%PREM_LAUNCHER_UPDATED%"
title Prem Lab
cd /d "%~dp0.."
if not exist "pyproject.toml" (
  echo This launcher has to stay inside the Prem Lab folder ^(as tools\prem-lab.bat^).
  pause
  exit /b 1
)

if not defined PREM_PORT set "PREM_PORT=8010"
set "URL=http://127.0.0.1:%PREM_PORT%/"

rem already running on this port? then just open it
set "CODE="
for /f %%c in ('curl.exe -s -o NUL -w "%%{http_code}" --max-time 2 "%URL%api/health" 2^>NUL') do set "CODE=%%c"
if "%CODE%"=="200" (
  echo Prem Lab is already running at %URL%
  if not defined PREM_NO_OPEN start "" "%URL%"
  exit /b 0
)

rem bring the project up to date first (tools\prem-update.ps1 says when it does not). This is one block on purpose: cmd reads a .bat file
rem line by line while it runs, so once the update may have replaced this file nothing more is read from it, and the launcher starts afresh
if not defined PREM_JUST_UPDATED if not defined PREM_NO_UPDATE if exist ".git" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0prem-update.ps1"
  if errorlevel 10 (
    endlocal & set "PREM_LAUNCHER_UPDATED=1" & "%~f0" %*
  )
)

rem what to run: the project's own environment first (made by "uv sync" or "py -m venv .venv"), then uv, then a prem on the PATH
set "PREM="
if exist ".venv\Scripts\prem.exe" set "PREM=.venv\Scripts\prem.exe"
if not defined PREM where uv >NUL 2>&1 && set "PREM=uv run prem"
if not defined PREM where prem >NUL 2>&1 && set "PREM=prem"
if not defined PREM (
  echo Prem Lab is not installed yet. In this folder, run:  uv sync
  echo ^(or, without uv:  py -m venv .venv  and then  .venv\Scripts\pip install -e .^)
  pause
  exit /b 1
)

set "OPEN="
if defined PREM_NO_OPEN set "OPEN=--no-open"
echo Starting Prem Lab at %URL%  ^(press Ctrl+C or close this window to stop it^)
echo.
%PREM% serve --port %PREM_PORT% %OPEN% %*
echo.
echo Prem Lab has stopped.
pause
