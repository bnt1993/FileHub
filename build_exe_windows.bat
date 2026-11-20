@echo off
setlocal
cd /d "%~dp0"
title FileHub VN - Build Windows EXE

echo ============================================
echo        FILEHUB VN - WINDOWS EXE BUILD

echo ============================================
echo.

where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python not found. Install Python 3.10 or later from python.org
        echo During install, enable "Add Python to PATH".
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

echo Checking Python version...
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required.
    pause
    exit /b 1
)

echo [1/4] Creating isolated environment...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON% -m venv .venv
    if errorlevel 1 goto FAIL
)

echo [2/4] Installing dependencies (requires internet first time)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto FAIL

echo [3/4] Packaging standalone application...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "FileHubVN" --icon "assets\filehub.ico" --add-data "assets\filehub.ico;assets" --distpath "dist" --workpath "build" --specpath "." "app.py"
if errorlevel 1 goto FAIL

echo [4/4] Done!
echo.
echo EXE: %CD%\dist\FileHubVN.exe
explorer "%CD%\dist"
pause
exit /b 0

:FAIL
echo.
echo Build failed. Review messages above.
pause
exit /b 1
