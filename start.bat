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

:: ── 1. Find Python ──────────────────────────────────────
set PYTHON=
for %%P in (python3 python) do (
    if "!PYTHON!"=="" (
        where %%P >nul 2>&1
        if !errorlevel! == 0 (
            for /f "tokens=*" %%V in ('%%P --version 2^>^&1') do (
                echo %%V | findstr /C:"Python 3" >nul
                if !errorlevel! == 0 (
                    set PYTHON=%%P
                )
            )
        )
    )
)

if "!PYTHON!"=="" (
    echo   [INFO] Python 3 not found. Downloading installer...
    curl -L -o python_installer.exe "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"
    if !errorlevel! neq 0 (
        echo   [ERROR] Download failed. Install Python from https://www.python.org/downloads/
        echo   Check "Add python.exe to PATH" during install, then re-run start.bat
        pause
        exit /b 1
    )
    echo   ...  Installing Python silently...
    start /wait python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del python_installer.exe
    set "NEW_PY_PATH=!LocalAppData!\Programs\Python\Python311\python.exe"
    if exist "!NEW_PY_PATH!" (
        set PYTHON="!NEW_PY_PATH!"
    ) else (
        echo   [WARNING] Restart this window and double-click start.bat again.
        pause
        exit /b 0
    )
)

for /f "tokens=*" %%V in ('!PYTHON! --version 2^>^&1') do echo   OK  %%V

:: ── 2. Virtual environment ──────────────────────────────
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
set VENV_PIP=venv\Scripts\pip.exe

%VENV_PYTHON% -m pip install --quiet --upgrade pip >nul 2>&1

:: ── 3. Dependencies ─────────────────────────────────────
echo   ...  Checking packages...
%VENV_PYTHON% -c "import feedparser, schedule, plyer, pystray; from PIL import Image" >nul 2>&1
if !errorlevel! neq 0 (
    echo   ...  Installing packages (first run ~30s)...
    %VENV_PIP% install --quiet -r requirements.txt
    if !errorlevel! neq 0 (
        echo   [ERROR] Package install failed. Check internet and retry.
        pause
        exit /b 1
    )
    echo   OK   Packages installed
) else (
    echo   OK   Packages ready
)

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
