@echo off
setlocal
cd /d "%~dp0"
title PISS ON THE WORLD
echo ============================================================
echo       PISS v0.1 // WADRRB // PISS ON THE WORLD
echo ============================================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m piss run cards\piss_on_the_world.piss --receipts receipts\piss
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python -m piss run cards\piss_on_the_world.piss --receipts receipts\piss
  ) else (
    echo ERROR: Python 3 was not found.
    pause
    exit /b 1
  )
)
echo.
echo Latest PISS receipts:
dir /b /o-d receipts\piss\*.json 2>nul
echo.
pause
