@echo off
setlocal
cd /d "%~dp0"

echo ======================================================================
echo  QueryTrellis - Full Backend ^& Frontend Verification Suite
echo ======================================================================

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Running setup.bat first...
    call "%~dp0setup.bat"
    if %ERRORLEVEL% neq 0 exit /b 1
)

set PYTHONPATH=.

echo [*] Running Python backend pytest suite...
".venv\Scripts\python.exe" -m pytest -v tests/ --cov=src --cov-report=term-missing
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Python backend tests failed.
    exit /b 1
)

echo [*] Running Frontend TypeScript typecheck...
call npm --prefix frontend run typecheck
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Frontend typecheck failed.
    exit /b 1
)

echo [PASS] All QueryTrellis tests and typechecks completed cleanly.
endlocal
