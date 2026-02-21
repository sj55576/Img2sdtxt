@echo off
REM Img2sdtxt - Setup Script for Windows
setlocal enabledelayedexpansion

echo.
echo ========================================
echo Img2sdtxt Setup Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

set VENV_DIR=venv

REM Create virtual environment
if not exist "!VENV_DIR!" (
    echo [INFO] Creating Python virtual environment...
    python -m venv !VENV_DIR!
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
) else (
    echo [INFO] Virtual environment already exists
)

REM Activate virtual environment
call "!VENV_DIR!\Scripts\activate.bat"

REM Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install requirements
if exist "requirements.txt" (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [SUCCESS] Setup completed successfully!
) else (
    echo [ERROR] requirements.txt not found
    pause
    exit /b 1
)

echo.
echo [INFO] Virtual environment: !VENV_DIR!
echo [INFO] To activate the environment, run: !VENV_DIR!\Scripts\activate.bat
echo [INFO] To start the application, run: run.bat
echo.
pause
