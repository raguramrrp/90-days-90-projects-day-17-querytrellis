@echo off
setlocal
cd /d "%~dp0"

echo ======================================================================
echo  QueryTrellis Studio - Full-Stack Launch (FastAPI + Next.js)
echo ======================================================================

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Running setup.bat first...
    call "%~dp0setup.bat"
    if %ERRORLEVEL% neq 0 exit /b 1
)

if not exist "frontend\node_modules" (
    echo [!] Frontend packages missing. Installing...
    call npm --prefix frontend install
    if %ERRORLEVEL% neq 0 exit /b 1
)

set PYTHONPATH=%~dp0
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

".venv\Scripts\python.exe" -m src.launcher %*
exit /b %ERRORLEVEL%
