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
    echo {"AZ_OPENAI_ENDPOINT":"","AZ_OPENAI_KEY":"","AZ_TRANSLATOR_LLM_DEPLOYMENT_NAME":"gpt-4o-mini","ELEVENLABS_API_KEY":"","ELEVENLABS_VOICE_ID":"","ELEVENLABS_OPTIMIZE_STREAMING_LATENCY":0} > env.json
)

if not exist app_config.json (
    echo Creating default app_config.json file...
    echo {"INPUT_LANGUAGE_NAME_FOR_PROMPT":"English","OUTPUT_LANGUAGE_NAME_FOR_PROMPT":"Portuguese","SCRIBE_LANGUAGE_CODE":"en","TTS_OUTPUT_ENABLED":true,"PERIODIC_SCRIBE_INTERVAL_S":3.0,"PERIODIC_SCRIBE_INTER_CHUNK_OVERLAP_MS":250,"FINAL_SCRIBE_PRE_ROLL_MS":500,"LLM_TRANSLATOR_CONTEXT_WINDOW_SIZE":5,"MAX_NATIVE_HISTORY_CHARS":5000,"MAX_TRANSLATED_HISTORY_CHARS":5000,"AZ_VAD_SILENCE_TIMEOUT_MS":500,"AZ_VAD_PRE_ROLL_MS":300} > app_config.json
)

echo.
echo Setup complete!
echo.
echo Would you like to run the application now? (Y/N)
set /p RUN_NOW=

if /i "%RUN_NOW%"=="Y" (
    echo.
    echo Starting Live Dubbing Application...
    python main.py
) else (
    echo.
    echo To start the application later, run:
    echo start.bat
    echo.
)

pause
