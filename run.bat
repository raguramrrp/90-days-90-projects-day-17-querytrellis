@echo off
setlocal

echo ======================================================================
echo  QueryTrellis - PostgreSQL Query Performance ^& Optimization Workbench
echo ======================================================================

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Running setup.bat first...
    call setup.bat
    if %ERRORLEVEL% neq 0 exit /b 1
)

set PYTHONPATH=.

echo [*] Starting QueryTrellis Streamlit Workbench...
echo [*] Local URL: http://127.0.0.1:8501
echo [*] Press CTRL+C in this window to stop the server.
echo ======================================================================

".venv\Scripts\python.exe" -m streamlit run app/main.py --server.address 127.0.0.1 --server.port 8501

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] QueryTrellis exited with error code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

endlocal
