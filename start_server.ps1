# AI Clip Generator - Web Server Startup Script (PowerShell)
# Run with: .\start_server.ps1

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  🎬 AI Clip Generator - Web Interface" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.8+ from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Check if Flask is installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
try {
    python -c "import flask" 2>&1 | Out-Null
    Write-Host "✅ Flask is installed" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Flask not found. Installing dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "✅ Dependencies installed" -ForegroundColor Green
}

Write-Host ""

# Get local IP address
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*"} | Select-Object -First 1).IPAddress

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Server Starting..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Access the web interface at:" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Local:  http://localhost:5000" -ForegroundColor White
if ($localIP) {
    Write-Host "   Network: http://$localIP:5000" -ForegroundColor White
}
Write-Host ""
Write-Host "💡 Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Start the Flask application
try {
    python app.py
} catch {
    Write-Host ""
    Write-Host "❌ Server failed to start. Check the error messages above." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

