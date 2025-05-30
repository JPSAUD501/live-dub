@echo off
echo ======================================
echo Live Dubbing Application - Setup
echo ======================================
echo.

set VENV_DIR=venv
set PYTHON_CMD=python

echo Checking Python installation...
where %PYTHON_CMD% >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python not found in PATH!
    echo Please install Python 3.8 or later from https://www.python.org/
    echo and ensure it is added to your PATH.
    pause
    exit /b 1
)

%PYTHON_CMD% --version
if %ERRORLEVEL% NEQ 0 (
    echo Error checking Python version.
    pause
    exit /b 1
)

echo.
echo Checking for updates...
echo.
git rev-parse --git-dir >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Git repository detected, checking for updates...
    echo.
    
    echo Fetching latest updates...
    git pull
    if %ERRORLEVEL% EQU 0 (
        echo ✓ Successfully updated to the latest version!
    ) else (
        echo ⚠ Failed to update automatically. You may continue with current version.
    )
) else (
    echo Not a git repository or git not installed. Skipping update check.
)
echo.

echo Creating virtual environment...
if not exist %VENV_DIR% (
    %PYTHON_CMD% -m venv %VENV_DIR%
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment!
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo.
echo Activating virtual environment...
call %VENV_DIR%\Scripts\activate
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment!
    pause
    exit /b 1
)

echo.
echo Installing/Updating dependencies...
python -m pip install --upgrade pip
if %ERRORLEVEL% NEQ 0 (
    echo Failed to upgrade pip!
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install required packages!
    pause
    exit /b 1
)

echo.
echo Creating default configuration files if not exist...

if not exist env.json (
    echo Creating default env.json file...
    echo {"AZ_OPENAI_ENDPOINT":"","AZ_OPENAI_KEY":"","ELEVENLABS_API_KEY":""} > env.json
)

if not exist app_config.json (
    echo Creating default app_config.json file...
    echo {"INPUT_LANGUAGE_NAME_FOR_PROMPT":"English","OUTPUT_LANGUAGE_NAME_FOR_PROMPT":"Portuguese","SCRIBE_LANGUAGE_CODE":"en", "TTS_LANGUAGE_CODE": "pt","TTS_OUTPUT_ENABLED":true,"ELEVENLABS_VOICE_ID":"CwhRBWXzGAHq8TQ4Fs17","PYAUDIO_INPUT_DEVICE_INDEX":null,"PYAUDIO_OUTPUT_DEVICE_NAME":null} > app_config.json
)

echo.
echo Setup complete! Starting application...
echo.

call go.bat
