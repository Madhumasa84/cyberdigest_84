@echo off
setlocal enabledelayedexpansion
title CyberDigest — One-click launcher

:: Always run from this script's folder (double-click safe)
cd /d "%~dp0"

echo.
echo   +==========================================+
echo   ^|      CyberDigest Agent                   ^|
echo   ^|   One-click threat intelligence          ^|
echo   +==========================================+
echo.

:: ── 1. Find Python 3.10+ ────────────────────────────────
set PYTHON=
for %%P in (python python3) do (
    if "!PYTHON!"=="" (
        where %%P >nul 2>&1
        if !errorlevel! == 0 (
            %%P -c "import sys; sys.exit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
            if !errorlevel! == 0 set PYTHON=%%P
        )
    )
)

if "!PYTHON!"=="" (
    where py >nul 2>&1
    if !errorlevel! == 0 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
        if !errorlevel! == 0 set PYTHON=py -3
    )
)

if "!PYTHON!"=="" (
    echo   [INFO] Python 3.10+ not found. Installing Python 3.12 with winget...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo   [ERROR] winget is unavailable. Install Python 3.10+ from:
        echo           https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )
    winget install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        echo   [ERROR] Python installation failed. Install Python 3.10+ manually.
        pause
        exit /b 1
    )
    set PYTHON=py -3.12
    !PYTHON! -c "import sys; sys.exit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
    if !errorlevel! neq 0 (
        echo   [INFO] Restart this window, then double-click start.bat again.
        pause
        exit /b 0
    )
)

for /f "tokens=*" %%V in ('!PYTHON! --version 2^>^&1') do echo   OK  %%V

:: ── 2. Virtual environment ──────────────────────────────
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
    if !errorlevel! neq 0 (
        echo   ...  Rebuilding an incompatible virtual environment...
        !PYTHON! -m venv --clear venv
        if !errorlevel! neq 0 (
            echo   [ERROR] Failed to rebuild the virtual environment.
            pause
            exit /b 1
        )
    )
)
if not exist "venv\Scripts\python.exe" (
    echo   ...  Creating virtual environment...
    !PYTHON! -m venv venv
    if !errorlevel! neq 0 (
        echo   [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo   OK   Virtual environment ready
)

set VENV_PYTHON=venv\Scripts\python.exe

%VENV_PYTHON% -m pip install --quiet --upgrade pip >nul 2>&1

:: ── 3. Dependencies ─────────────────────────────────────
echo   ...  Verifying pinned packages...
%VENV_PYTHON% -m pip install --quiet --editable .
if !errorlevel! neq 0 (
    echo   [ERROR] Package install failed. Check internet and retry.
    pause
    exit /b 1
)
%VENV_PYTHON% -m pip check
if !errorlevel! neq 0 (
    echo   [ERROR] Installed packages have dependency conflicts.
    pause
    exit /b 1
)
echo   OK   Packages ready

:: ── 4. Launch ───────────────────────────────────────────
echo.
echo   Starting CyberDigest...
echo   1) Fetches news
echo   2) Opens the HTML digest in your browser
echo   3) Keeps a tray icon for later
echo.
echo   If the browser does not open, check the "Report ready:" path below
echo   and double-click that .html file in the reports folder.
echo.

:: Force desktop browser behavior (never treat as headless server)
set CYBERDIGEST_HEADLESS=0

%VENV_PYTHON% news_agent.py

echo.
echo   Done for this session.
echo   Reports folder: %cd%\reports
if exist "reports\index.html" (
  echo   Opening archive index...
  start "" "%cd%\reports\index.html"
)
echo   Status file:    %cd%\status.txt
echo.
pause
