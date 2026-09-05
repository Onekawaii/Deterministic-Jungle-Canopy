@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m piss run cards\project_check.piss --receipts receipts\piss
) else (
  python -m piss run cards\project_check.piss --receipts receipts\piss
)
pause
