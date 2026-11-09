@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ======================================================================
echo  QueryTrellis Studio - Natural Language SQL ^& Visual Learning Workbench
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

:: 3. Install Python backend dependencies
echo [*] Installing Python dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    exit /b 1
)
echo [OK] Python dependencies installed successfully.

:: 4. Install Next.js frontend dependencies
where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js / npm was not found on PATH.
    echo Please install Node.js 20+ from https://nodejs.org/ and add it to PATH.
    exit /b 1
)

echo [*] Installing Next.js frontend packages...
call npm --prefix frontend install
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install frontend packages.
    exit /b 1
)
echo [OK] Frontend packages installed successfully.

:: 5. Build frontend assets for fast startup
echo [*] Building Next.js production bundle...
call npm --prefix frontend run build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Frontend production build failed.
    exit /b 1
)

:: 6. Create data/sample directories and .env if absent (never overwrite existing .env)
if not exist "data" mkdir data
if not exist "data\sandboxes" mkdir data\sandboxes

if not exist ".env" (
    echo [*] Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo [OK] .env created. Edit .env only if connecting live external DBs/models.
) else (
    echo [OK] Existing .env preserved.
)

:: 7. Materialize Demo DuckDB Sandbox & Bundled Multi-Format Samples
echo [*] Generating Demo Enterprise DuckDB Sandbox ^& Sample Datasets...
".venv\Scripts\python.exe" -c "from src.connectors.demo_sandbox import ensure_demo_duckdb, ensure_sample_export_files; ensure_demo_duckdb(); ensure_sample_export_files()"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to build Demo sandbox dataset.
    exit /b 1
)
echo [OK] Demo sandbox and sample_data/ ready.

echo ======================================================================
echo  QueryTrellis Setup Complete
echo    - Launch Full Workbench:  run.bat
echo    - Run Test Suite:         test.bat
echo ======================================================================

endlocal
