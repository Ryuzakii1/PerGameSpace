@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo Game Library Server Launcher
echo ==========================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo Python found: 
python --version

REM Check if app.py exists
if not exist "app.py" (
    echo ERROR: app.py not found in current directory
    echo Please run the setup batch file first to create the application
    pause
    exit /b 1
)

REM Check if Flask is installed
echo Checking Flask installation...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Flask not found. Installing Flask...
    pip install flask
    if errorlevel 1 (
        echo ERROR: Failed to install Flask
        echo Please try running: pip install flask
        pause
        exit /b 1
    )
    echo Flask installed successfully!
) else (
    echo Flask is already installed
)

REM Create directories if they don't exist
if not exist "templates" (
    echo WARNING: templates directory not found
    echo Please run the setup batch file first
    pause
    exit /b 1
)

if not exist "uploads" (
    echo Creating uploads directory...
    mkdir uploads
)

REM Display startup information
echo.
echo ==========================================
echo Starting Game Library Server...
echo ==========================================
echo Server will be available at:
echo   http://localhost:5000
echo   http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server
echo ==========================================
echo.

REM Start the Flask application
python app.py

REM This will only execute if the Python script exits
echo.
echo ==========================================
echo Server stopped
echo ==========================================
pause