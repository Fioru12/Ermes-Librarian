@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo [INFO] Controllo Ollama...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [ATTESA] Avvio Ollama...
    start /B "" "ollama serve"
    for /L %%i in (1,1,15) do (
        timeout /t 2 /nobreak >nul
        curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
        if !errorlevel! equ 0 goto OLLAMA_OK
    )
)
:OLLAMA_OK

set "PYTHON_EXE=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

start "" "%PYTHON_EXE%" -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1

timeout /t 5 /nobreak >nul
start "" "http://localhost:8502"
endlocal
exit 0
