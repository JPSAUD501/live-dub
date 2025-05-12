@echo off
echo ======================================
echo Live Dubbing Application - Launcher
echo ======================================

set VENV_DIR=venv

if not exist %VENV_DIR% (
    echo Virtual environment not found!
    echo Please run setup.bat first to set up the application.
    pause
    exit /b 1
)

echo Activating virtual environment...
call %VENV_DIR%\Scripts\activate
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment!
    pause
    exit /b 1
)

echo Starting Live Dubbing Application...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo Application exited with errors.
    pause
)
