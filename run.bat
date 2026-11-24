@echo off
REM ================================================================
REM BourseView Launcher (ASCII-only for maximum compatibility)
REM All Persian output is handled by launch.py
REM ================================================================
cd /d "%~dp0"

set PYTHON_CMD=

REM Try py launcher first (comes with python.org installer)
where py >nul 2>nul
if %errorlevel%==0 (
    py --version >nul 2>nul
    if not errorlevel 1 (
        set PYTHON_CMD=py
        goto :found
    )
)

REM Try python
where python >nul 2>nul
if %errorlevel%==0 (
    python --version >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0)" >nul 2>nul
        if not errorlevel 1 (
            set PYTHON_CMD=python
            goto :found
        )
    )
)

REM Try python3
where python3 >nul 2>nul
if %errorlevel%==0 (
    python3 --version >nul 2>nul
    if not errorlevel 1 (
        python3 -c "import sys; sys.exit(0)" >nul 2>nul
        if not errorlevel 1 (
            set PYTHON_CMD=python3
            goto :found
        )
    )
)

REM No working Python found
echo.
echo  ================================================================
echo   ERROR: Python not found or not working!
echo  ================================================================
echo.
echo   Your system has Python from Microsoft Store which has limited
echo   access (Access Denied errors).
echo.
echo   SOLUTION: Install Python from the official website:
echo     1. Go to: https://www.python.org/downloads/
echo     2. Download Python 3.12 or newer
echo     3. During installation, CHECK the box:
echo        "Add Python to PATH"
echo     4. Restart this file after installation
echo.
pause
exit /b 1

:found
REM Delegate everything to launch.py (handles deps, banner, browser, proxy)
%PYTHON_CMD% launch.py %*

REM If launch.py crashed, show message
if errorlevel 1 (
    echo.
    echo   BourseView stopped unexpectedly.
    echo   Check the error message above.
)
pause
