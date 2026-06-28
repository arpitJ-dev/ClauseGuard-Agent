@echo off
echo Activating Legal-LM Virtual Environment...
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"

REM Check if virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Error: Virtual environment not found at %VENV_DIR%
    echo Please ensure the 'venv' folder exists in the project directory.
    pause
    exit /b 1
)

REM Activate the virtual environment
echo Virtual environment found at: %VENV_DIR%
echo Activating...
call "%VENV_DIR%\Scripts\activate.bat"

REM Verify activation
if defined VIRTUAL_ENV (
    echo.
    echo ✅ Virtual environment activated successfully!
    echo Current Python: %VIRTUAL_ENV%\Scripts\python.exe
    echo.
    echo You can now run: pip install -r requirements.txt
    echo.
    cmd /k
) else (
    echo.
    echo ❌ Failed to activate virtual environment
    echo.
    pause
)

