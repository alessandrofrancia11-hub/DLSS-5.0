@echo off
rem Avvia la DLSS 5 Dashboard (serve Python 3.10+: https://www.python.org/downloads/)
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m dlss5_dashboard %*
) else (
  python -m dlss5_dashboard %*
)
if errorlevel 1 pause
