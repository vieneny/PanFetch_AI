@echo off
setlocal
cd /d "%~dp0"

set "SILENT=0"
if /i "%~1"=="--silent" set "SILENT=1"
set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONW=.venv\Scripts\pythonw.exe"
for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "LOG_DATE=%%I"
set "LOG_DIR=logs\%LOG_DATE%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
set "LOG=%LOG_DIR%\startup.log"
set "RUN_LOG=%TEMP%\panfetch_ai_startup_%RANDOM%_%RANDOM%.log"

if not exist "%PYTHON%" (
    where uv >nul 2>nul
    if errorlevel 1 goto error
    if "%SILENT%"=="1" (
        uv sync --python 3.12 --system-certs >>"%RUN_LOG%" 2>&1
    ) else (
        uv sync --python 3.12 --system-certs
    )
    if errorlevel 1 goto error
)

"%PYTHON%" -c "import PySide6, langgraph, mcp, requests, truststore, win32crypt, panfetch_ai" >nul 2>>"%RUN_LOG%"
if errorlevel 1 (
    if "%SILENT%"=="1" (
        uv sync --python 3.12 --system-certs >>"%RUN_LOG%" 2>&1
    ) else (
        uv sync --python 3.12 --system-certs
    )
    if errorlevel 1 goto error
)

if "%SILENT%"=="1" (
    start "" /wait "%PYTHONW%" -m panfetch_ai 2>>"%RUN_LOG%"
) else (
    "%PYTHON%" -m panfetch_ai 2>>"%RUN_LOG%"
)
if errorlevel 1 goto error
if exist "%RUN_LOG%" del /q "%RUN_LOG%" >nul 2>nul
if exist "%LOG%" del /q "%LOG%" >nul 2>nul
exit /b 0

:error
copy /y "%RUN_LOG%" "%LOG%" >nul 2>nul
if "%SILENT%"=="1" exit /b 1
echo.
echo PanFetch AI startup failed. Details:
if exist "%RUN_LOG%" type "%RUN_LOG%"
echo.
echo Log file: %LOG%
pause
exit /b 1
