@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_CANOPY_WINDOWS.ps1" %*
exit /b %errorlevel%
