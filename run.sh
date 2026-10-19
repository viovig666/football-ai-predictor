#!/bin/bash
# run.sh — Quick startup script for FootPredict AI

echo "⚽ FootPredict AI — Starting..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt
echo "✅ Dependencies installed"

# Pre-train the model
echo "🧠 Training AI model..."
python3 -m ai.train

# Run the Flask app
echo ""
echo "🚀 Starting FootPredict AI on http://localhost:5000"
echo "   Press Ctrl+C to stop"
echo ""
python3 app.py
