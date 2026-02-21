#!/bin/bash

# Img2sdtxt - Setup Script for Linux/macOS
set -e

# Color codes
BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "========================================"
echo "Img2sdtxt Setup Script"
echo "========================================"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ using:"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-venv python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${BLUE}[INFO]${NC} Python version: $PYTHON_VERSION"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR="venv"

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${BLUE}[INFO]${NC} Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}[SUCCESS]${NC} Virtual environment created"
else
    echo -e "${BLUE}[INFO]${NC} Virtual environment already exists"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo -e "${BLUE}[INFO]${NC} Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install requirements
if [ -f "requirements.txt" ]; then
    echo -e "${BLUE}[INFO]${NC} Installing dependencies..."
    pip install -r requirements.txt
    echo -e "${GREEN}[SUCCESS]${NC} Setup completed successfully!"
else
    echo -e "${RED}[ERROR]${NC} requirements.txt not found"
    exit 1
fi

echo ""
echo -e "${BLUE}[INFO]${NC} Virtual environment: $VENV_DIR"
echo -e "${BLUE}[INFO]${NC} To activate the environment, run: source $VENV_DIR/bin/activate"
echo -e "${BLUE}[INFO]${NC} To start the application, run: ./run.sh"
echo ""
