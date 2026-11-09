@echo off
setlocal

echo ======================================================================
echo  QueryTrellis - Automated Test Suite
echo ======================================================================

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Running setup.bat first...
    call setup.bat
    if %ERRORLEVEL% neq 0 exit /b 1
)

set PYTHONPATH=.

echo [*] Running pytest suite with coverage...
".venv\Scripts\python.exe" -m pytest -v tests/ --cov=src --cov-report=term-missing

if %ERRORLEVEL% neq 0 (
    echo [FAIL] Test suite failed.
    exit /b %ERRORLEVEL%
)

echo [PASS] Automated test execution completed cleanly.
endlocal
