@echo off
chcp 65001 >nul
cd /d "%~dp0.."

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERRORE] Ambiente virtuale non trovato in .venv.
    pause
    exit /b 1
)

echo Running WinSarp tests...
"%PYTHON_EXE%" -m pytest tests/test_winsarp.py -q
pause
