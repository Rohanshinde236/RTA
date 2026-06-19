@echo off
REM ============================================================
REM  RTA Monitoring System - one-click launcher
REM  Just double-click this file. No commands to type.
REM ============================================================
cd /d "%~dp0"
title RTA Monitor

echo ============================================
echo    RTA Monitoring System
echo ============================================
echo.

REM --- 1. Check Python is installed -------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python is not installed ^(or not on PATH^).
  echo.
  echo     Please install Python 3.11 from:
  echo        https://www.python.org/downloads/
  echo     During install, TICK the box "Add Python to PATH".
  echo     Then double-click this file again.
  echo.
  pause
  exit /b 1
)

REM --- 2. First-time setup (runs only once) -----------------------------------
if not exist ".setup_done" (
  echo First-time setup - installing components. This can take a few minutes...
  echo.
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [!] Could not install Python packages. Check your internet connection and try again.
    pause
    exit /b 1
  )
  python -m playwright install chromium
  if errorlevel 1 (
    echo.
    echo [!] Could not install the browser component. Check your internet connection and try again.
    pause
    exit /b 1
  )
  echo done> .setup_done
  echo.
  echo Setup complete.
  echo.
)

REM --- 3. Open the dashboard in the browser once the server is up -------------
start "" cmd /c "timeout /t 5 >nul & start http://localhost:5000"

REM --- 4. Start the app (keep this window open while using it) -----------------
echo Starting RTA Monitor...
echo The dashboard will open in your browser at  http://localhost:5000
echo.
echo  *** Keep THIS window open while using the app. Close it to stop. ***
echo.
python app.py

echo.
echo RTA Monitor has stopped.
pause
