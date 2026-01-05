#!/bin/bash
# AI Clip Generator - Web Server Startup Script (Linux/Mac)
# Run with: ./start.sh or bash start.sh

echo ""
echo "============================================================"
echo "  🎬 AI Clip Generator - Web Interface"
echo "============================================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed"
    echo ""
    echo "Please install Python 3.8+ from: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ Python found: $PYTHON_VERSION"
echo ""

# Check if Flask is installed
echo "Checking dependencies..."
if ! python3 -c "import flask" &> /dev/null; then
    echo "⚠️  Flask not found. Installing dependencies..."
    python3 -m pip install -r requirements.txt --quiet
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
    echo "✅ Dependencies installed"
else
    echo "✅ Flask is installed"
fi

echo ""

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || echo "")

echo "============================================================"
echo "  Server Starting..."
echo "============================================================"
echo ""
echo "📍 Access the web interface at:"
echo ""
echo "   Local:  http://localhost:5000"
if [ ! -z "$LOCAL_IP" ]; then
    echo "   Network: http://$LOCAL_IP:5000"
fi
echo ""
echo "💡 Press Ctrl+C to stop the server"
echo ""
echo "============================================================"
echo ""

# Start the Flask application
python3 app.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Server failed to start. Check the error messages above."
    exit 1
fi

