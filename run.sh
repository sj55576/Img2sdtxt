#!/bin/bash

# Img2sdtxt - FastAPI Application Launcher for Linux/macOS
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Print header
echo ""
echo "========================================"
echo "Img2sdtxt Application Launcher"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8+ using:"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-venv python3-pip"
    echo "  macOS: brew install python3"
    echo "  Or visit: https://www.python.org/"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python version: $PYTHON_VERSION"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

VENV_DIR="venv"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        error "Failed to create virtual environment"
        exit 1
    fi
    success "Virtual environment created"
else
    info "Virtual environment already exists"
fi

# Activate virtual environment
info "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
if [ $? -ne 0 ]; then
    error "Failed to activate virtual environment"
    exit 1
fi

# Upgrade pip
info "Upgrading pip..."
python -m pip install --upgrade pip --quiet
if [ $? -ne 0 ]; then
    error "Failed to upgrade pip"
    exit 1
fi

# Install requirements
if [ -f "requirements.txt" ]; then
    info "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        error "Failed to install dependencies"
        exit 1
    fi
    success "Dependencies installed successfully"
else
    error "requirements.txt not found"
    exit 1
fi

# Check for .env file
if [ ! -f ".env" ]; then
    info ".env file not found. Creating default .env..."
    cat > .env << 'EOF'
# LLM Server Configuration
LLM_SERVER_URL=http://localhost:1234/v1
LLM_MODEL=gpt-3.5-turbo

# Stable Diffusion API Configuration
SD_API_URL=http://localhost:7860

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false

# HTTPS Configuration
HTTPS_ENABLED=false
#SSL_CERTFILE=/path/to/cert.pem
#SSL_KEYFILE=/path/to/key.pem
EOF
    success "Default .env file created. Please configure it as needed."
    echo ""
fi

# Read settings from .env (if it exists)
API_PORT_VAL=$(grep -E '^API_PORT=' .env 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]')
API_PORT_VAL="${API_PORT_VAL:-8000}"
HTTPS_VAL=$(grep -E '^HTTPS_ENABLED=' .env 2>/dev/null | cut -d'=' -f2 | tr -d '[:space:]')
if [ "$(echo "$HTTPS_VAL" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
    APP_PROTOCOL="https"
else
    APP_PROTOCOL="http"
fi

# Display configuration
echo ""
echo "========================================"
echo "Configuration"
echo "========================================"
info "API will start on: ${APP_PROTOCOL}://localhost:${API_PORT_VAL}"
info "LLM Server URL: http://localhost:1234/v1"
info "SD API URL: http://localhost:7860"
echo ""
warning "Make sure the following services are running:"
echo "  - LLM Server (default: http://localhost:1234)"
echo "  - Stable Diffusion API (default: http://localhost:7860)"
echo ""

# Start the application
info "Starting Img2sdtxt application..."
echo ""
python main.py

# Cleanup message
echo ""
info "Application terminated"
