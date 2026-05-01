@echo off
REM Img2sdtxt - FastAPI Application Launcher for Windows
setlocal enabledelayedexpansion

echo.
echo ========================================
echo Img2sdtxt Application Launcher
echo ========================================
echo.

REM Set up color codes for output
set "INFO=[INFO]"
set "ERROR=[ERROR]"
set "SUCCESS=[SUCCESS]"

REM Check if Python is installed
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo %ERROR% Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

set VENV_DIR=venv

REM Create virtual environment if it doesn't exist
if not exist "!VENV_DIR!" (
    echo %INFO% Creating Python virtual environment...
    python -m venv !VENV_DIR!
    if !errorlevel! neq 0 (
        echo %ERROR% Failed to create virtual environment
        pause
        exit /b 1
    )
    echo %SUCCESS% Virtual environment created
) else (
    echo %INFO% Virtual environment already exists
)

REM Activate virtual environment
echo %INFO% Activating virtual environment...
call "!VENV_DIR!\Scripts\activate.bat"
if !errorlevel! neq 0 (
    echo %ERROR% Failed to activate virtual environment
    pause
    exit /b 1
)

REM Upgrade pip
echo %INFO% Upgrading pip...
python -m pip install --upgrade pip --quiet
if !errorlevel! neq 0 (
    echo %ERROR% Failed to upgrade pip
    pause
    exit /b 1
)

REM Install requirements
if exist "requirements.txt" (
    echo %INFO% Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo %ERROR% Failed to install dependencies
        pause
        exit /b 1
    )
    echo %SUCCESS% Dependencies installed successfully
) else (
    echo %ERROR% requirements.txt not found
    pause
    exit /b 1
)

REM Check for .env file
if not exist ".env" (
    echo %INFO% .env file not found. Creating default .env...
    (
        echo # LLM Server Configuration
        echo LLM_SERVER_URL=http://localhost:1234/v1
        echo LLM_MODEL=gpt-3.5-turbo
        echo.
        echo # Stable Diffusion API Configuration
        echo SD_API_URL=http://localhost:7860
        echo.
        echo # API Server Configuration
        echo API_HOST=0.0.0.0
        echo API_PORT=8000
        echo DEBUG=false
        echo.
        echo # HTTPS Configuration
        echo HTTPS_ENABLED=false
        echo #SSL_CERTFILE=/path/to/cert.pem
        echo #SSL_KEYFILE=/path/to/key.pem
    ) > .env
    echo %SUCCESS% Default .env file created. Please configure it as needed.
    echo.
)

REM Read HTTPS_ENABLED and API_PORT from .env
set APP_PROTOCOL=http
set APP_PORT=8000
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="HTTPS_ENABLED" (
        if /i "%%B"=="true" set APP_PROTOCOL=https
    )
    if /i "%%A"=="API_PORT" set APP_PORT=%%B
)

REM Display configuration
echo.
echo ========================================
echo Configuration
echo ========================================
echo %INFO% API will start on: %APP_PROTOCOL%://localhost:%APP_PORT%
echo %INFO% LLM Server URL: http://localhost:1234/v1
echo %INFO% SD API URL: http://localhost:7860
echo.
echo %INFO% Make sure the following services are running:
echo   - LLM Server (default: http://localhost:1234)
echo   - Stable Diffusion API (default: http://localhost:7860)
echo.

REM Start the application
echo %INFO% Starting Img2sdtxt application...
echo.
python main.py

REM Cleanup
echo.
echo %INFO% Application terminated
pause
exit /b 0
