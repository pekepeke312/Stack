@echo off
setlocal
cd /d "%~dp0"
set "STACK_PORT=8050"
REM Difficulty: increase these values to make the game faster.
set "STACK_BASE_SPEED=2.0"
set "STACK_SPEED_GAIN=0.32"
set "STACK_EXTRA_AFTER=12"
set "STACK_EXTRA_GAIN=0.20"
REM Optional: to fix your PC LAN IP, remove REM and change this address.
REM set "STACK_PUBLIC_HOST=192.168.1.100"
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :failure
)
echo [2/3] Installing / verifying requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failure
echo [3/3] Launching Stack Duel...
echo Open on PC: http://localhost:%STACK_PORT%
start "" "http://localhost:%STACK_PORT%"
".venv\Scripts\python.exe" stack_duel_dash.py
if errorlevel 1 goto :failure
pause
exit /b 0
:failure
echo.
echo Failed to start. Check Python 3.10+ is installed and Internet is available for initial setup.
pause
exit /b 1
