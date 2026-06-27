@echo off
setlocal enabledelayedexpansion
title CyberDigest — Automated Threat Intelligence

echo.
echo   +==========================================+
echo   ^|      CyberDigest Agent                   ^|
echo   ^|   Automated Threat Intelligence          ^|
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
    echo   [INFO] Python 3 not found. Attempting automatic installation...
    echo   ...  Downloading Python installer ^(this may take a minute^)...
    curl -L -o python_installer.exe "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"
    if !errorlevel! neq 0 (
        echo   [ERROR] Failed to download Python. Check your internet connection.
        pause
        exit /b 1
    )
    
    echo   ...  Installing Python silently ^(this may take a few minutes^)...
    start /wait python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del python_installer.exe
    
    echo   ...  Python installed!
    
    :: Try to locate the newly installed Python
    set "NEW_PY_PATH=!LocalAppData!\Programs\Python\Python311\python.exe"
    if exist "!NEW_PY_PATH!" (
        set PYTHON="!NEW_PY_PATH!"
    ) else (
        echo   [WARNING] Python was installed, but you need to restart this window to use it.
        echo   Please close this window and double-click start.bat again.
        pause
        exit /b 0
    )
)

for /f "tokens=*" %%V in ('!PYTHON! --version 2^>^&1') do echo   OK  %%V found

:: ── 2. Create virtual environment ────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo   ...  Creating virtual environment...
    !PYTHON! -m venv venv
    if !errorlevel! neq 0 (
        echo   [ERROR] Failed to create virtual environment.
        echo   Try running: !PYTHON! -m pip install feedparser schedule plyer
        pause
        exit /b 1
    )
    echo   OK   Virtual environment created
)

set VENV_PYTHON=venv\Scripts\python.exe
set VENV_PIP=venv\Scripts\pip.exe

:: ── 3. Upgrade pip ────────────────────────────────────────
%VENV_PYTHON% -m pip install --quiet --upgrade pip >nul 2>&1

:: ── 4. Install dependencies ───────────────────────────────
echo   ...  Checking dependencies...
%VENV_PYTHON% -c "import feedparser, schedule, plyer" >nul 2>&1
if !errorlevel! neq 0 (
    echo   ...  Installing packages ^(first run, takes ~30 seconds^)...
    %VENV_PIP% install --quiet -r requirements.txt
    if !errorlevel! neq 0 (
        echo   [ERROR] Package installation failed.
        echo   Check your internet connection and try again.
        pause
        exit /b 1
    )
    echo   OK   All packages installed
) else (
    echo   OK   All packages ready
)

:: ── 5. Run the agent ──────────────────────────────────────
echo.
echo   Fetching your cybersecurity digest...
echo   Your browser will open with the report automatically.
echo   The agent will run every 3 days in the background.
echo   You can close this window after setup completes.
echo.

%VENV_PYTHON% news_agent.py

echo.
echo   Done! CyberDigest is running in the background.
echo   Check status.txt anytime to see the last run info.
echo.
pause
