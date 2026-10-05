@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run install.bat first.
    pause & exit /b 1
)
:: pythonw = no console window. Use "TexUp.bat --headless" to run in the console instead.
if "%~1"=="" (
    start "" ".venv\Scripts\pythonw.exe" -m texup
) else (
    ".venv\Scripts\python.exe" -m texup %*
)
