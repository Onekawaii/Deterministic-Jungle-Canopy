@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_HARDENED_AUTONOMOUS_BUILD.ps1" %*
exit /b %errorlevel%
