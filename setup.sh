#!/bin/bash

# CI/CD Anomaly Detection System - Setup Script

set -e

echo "============================================================"
echo "🤖 CI/CD Anomaly Detection System - Setup"
echo "============================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "🔍 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.8"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then 
    echo -e "${RED}❌ Python 3.8+ required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python $PYTHON_VERSION${NC}"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠️  Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo ""
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Dependencies installed${NC}"
else
    echo -e "${RED}❌ Failed to install dependencies${NC}"
    exit 1
fi

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p data/metrics data/anomalies data/reports models logs

echo -e "${GREEN}✅ Directories created${NC}"

# Setup environment file
echo ""
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.template .env
    echo -e "${GREEN}✅ .env file created${NC}"
    echo -e "${YELLOW}⚠️  Please edit .env with your credentials${NC}"
else
    echo -e "${YELLOW}⚠️  .env file already exists${NC}"
fi

# Run demo
echo ""
echo "🎮 Would you like to run the demo? (y/n)"
read -r response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo ""
    echo "🚀 Running demo..."
    python demo.py
fi

# Summary
echo ""
echo "============================================================"
echo "✅ Setup Complete!"
echo "============================================================"
echo ""
echo "📋 What's next?"
echo ""
echo "1. Configure your credentials in .env:"
echo "   ${YELLOW}nano .env${NC}"
echo ""
echo "2. Run the demo:"
echo "   ${YELLOW}python demo.py${NC}"
echo ""
echo "3. Start the API server:"
echo "   ${YELLOW}python api/app.py${NC}"
echo ""
echo "4. Start the scheduler:"
echo "   ${YELLOW}python scheduler.py${NC}"
echo ""
echo "5. Or use Docker Compose:"
echo "   ${YELLOW}docker-compose up -d${NC}"
echo ""
echo "📚 Documentation:"
echo "   • README.md - Full documentation"
echo "   • API.md - API reference"
echo "   • http://localhost:3000 - Grafana dashboard"
echo ""
echo "🎯 Quick test API:"
echo "   ${YELLOW}curl http://localhost:5000/health${NC}"
echo ""
