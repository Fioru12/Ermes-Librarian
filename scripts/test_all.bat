@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

set "PYTHON_EXE=.venv-ermes\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERRORE] Ambiente virtuale non trovato in .venv-ermes.
    pause
    exit /b 1
)

echo [INFO] Esecuzione test unitari...
REM --ignore=tests/test_quality.py rimosso: quel file non esiste piu'.
"%PYTHON_EXE%" -m pytest tests\ -v --tb=short ^
    --ignore=tests/test_integration.py

pause
endlocal
