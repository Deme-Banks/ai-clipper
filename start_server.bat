@echo off
title AI Clip Generator - Web Server
color 0A

echo.
echo ============================================================
echo   🎬 AI Clip Generator - Web Interface
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Check if required packages are installed
echo Checking dependencies...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Flask not found. Installing dependencies...
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo ❌ Failed to install dependencies
        pause
        exit /b 1
    )
    echo ✅ Dependencies installed
) else (
    echo ✅ Flask is installed
)

echo.

REM Get local IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set LOCAL_IP=%%a
    goto :found_ip
)
:found_ip
set LOCAL_IP=%LOCAL_IP:~1%

echo ============================================================
echo   Server Starting...
echo ============================================================
echo.
echo 📍 Access the web interface at:
echo.
echo    Local:  http://localhost:5000
if not "%LOCAL_IP%"=="" (
    echo    Network: http://%LOCAL_IP%:5000
)
echo.
echo 💡 Press Ctrl+C to stop the server
echo.
echo ============================================================
echo.

REM Start the Flask application
python app.py

if errorlevel 1 (
    echo.
    echo ❌ Server failed to start. Check the error messages above.
    pause
)

