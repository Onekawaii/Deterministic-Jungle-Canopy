@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

%PY% tests\test_piss.py -v
if errorlevel 1 goto :fail

%PY% -m piss check cards\piss_on_the_world.piss
if errorlevel 1 goto :fail

echo.
echo VERIFY PISS PASS
pause
exit /b 0

:fail
echo.
echo VERIFY PISS FAILED
pause
exit /b 1
