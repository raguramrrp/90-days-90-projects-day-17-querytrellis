@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo  QueryTrellis - PostgreSQL Query Performance ^& Optimization Workbench
echo  Windows Setup and Environment Initialization
echo ======================================================================

:: 1. Verify Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on PATH.
    echo Please install Python 3.11+ from https://www.python.org/ and add it to PATH.
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo [*] Detected %PYTHON_VER%

:: 2. Create project virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment (.venv) already exists.
)

:: 3. Install dependencies
echo [*] Installing dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)
echo [OK] Dependencies installed successfully.

:: 4. Create data directory and .env if absent (never overwrite existing .env)
if not exist "data" mkdir data

if not exist ".env" (
    echo [*] Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo [OK] .env created. Edit .env to set your PostgreSQL PGPASSWORD if required.
) else (
    echo [OK] Existing .env preserved.
)

:: 5. Attempt sample database initialization if PostgreSQL credentials are configured
echo [*] Checking PostgreSQL sample database setup...
".venv\Scripts\python.exe" scripts/setup_sample_db.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [INFO] Automatic PostgreSQL sample seeding skipped or requires configuration.
    echo        Configure PGHOST/PGPORT/PGUSER/PGPASSWORD in .env, then run:
    echo          .venv\Scripts\python.exe scripts\setup_sample_db.py
    echo        Or initialize an isolated local cluster on port 55432:
    echo          .venv\Scripts\python.exe scripts\local_pg_cluster.py start --port 55432
    echo          .venv\Scripts\python.exe scripts\setup_sample_db.py --host 127.0.0.1 --port 55432
) else (
    echo [OK] PostgreSQL sample database verified and populated.
)

echo ======================================================================
echo  QueryTrellis Setup Complete
echo    - Launch Workbench:  run.bat
echo    - Run Test Suite:    test.bat
echo ======================================================================

endlocal
