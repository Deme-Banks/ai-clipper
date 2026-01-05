@echo off
title AI Clip Generator
color 0A

echo.
echo ============================================================
echo   🎬 AI Clip Generator - Web Interface
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Install from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python found
echo Checking dependencies...

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo ❌ Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Get IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do set IP=%%a
set IP=%IP:~1%

echo.
echo ============================================================
echo   Server Starting...
echo ============================================================
echo.
echo 📍 Access at:
echo    Local:  http://localhost:5000
if not "%IP%"=="" echo    Network: http://%IP%:5000
echo.
echo 💡 Press Ctrl+C to stop
echo ============================================================
echo.

python app.py

if errorlevel 1 (
    echo.
    echo ❌ Server failed to start
    pause
)

