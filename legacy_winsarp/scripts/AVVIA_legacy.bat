@echo off
chcp 65001 >nul
title Ermes - Avvio Rapido
setlocal EnableExtensions EnableDelayedExpansion

echo ========================================
echo   Ermes - Enterprise Knowledge Hub
echo ========================================
echo.

cd /d "%~dp0.."

echo [1/4] Verifica ambiente virtuale...
if not exist ".venv\Scripts\python.exe" (
    echo [ERRORE] Ambiente virtuale non trovato in .venv.
    echo Esegui prima lo script di setup.
    pause
    exit /b 1
)
echo [OK] Ambiente virtuale trovato

echo.
echo [2/4] Verifica Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Ollama non trovato. Installa Ollama.
    pause
    exit /b 1
)
echo [OK] Ollama installato

echo.
echo [3/4] Avvia Ollama se necessario e attendi che sia pronto...
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [ATTESA] Ollama non in esecuzione. Avvio...
    start /B "" ollama serve
    
    :: Loop di attesa fino a 30 secondi (15 tentativi x 2 sec)
    set OLLAMA_READY=0
    for /L %%i in (1,1,15) do (
        timeout /t 2 /nobreak >nul
        curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
        if !errorlevel! equ 0 (
            set OLLAMA_READY=1
            goto OLLAMA_OK
        )
    )
    :OLLAMA_OK
    if !OLLAMA_READY! neq 1 (
        echo [ERRORE] Ollama non si e' avviato dopo 30 secondi.
        pause
        exit /b 1
    )
)
echo [OK] Ollama in esecuzione

echo.
echo [4/4] Avvio Backend (uvicorn)...
set PYTHON_CMD=.venv\Scripts\python.exe
echo [INFO] Uso ambiente virtuale: .venv

start /B "Ermes" "%PYTHON_CMD%" -m uvicorn api:app --host 0.0.0.0 --port 8504
echo [ATTESA] Attendo che il server sia pronto (fino a 30 secondi)...

set READY=0
for /L %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    curl -s http://127.0.0.1:8504/health >nul 2>&1
    if !errorlevel! equ 0 (
        set READY=1
        echo [OK] Server pronto! Apro il browser...
        start http://127.0.0.1:8504
        goto :RUNNING
    )
)

if !READY! neq 1 (
    echo [AVVISO] Server non risponde dopo 30s. Apro comunque il browser...
    start http://127.0.0.1:8504
)

:RUNNING
echo.
echo --- Ermes attivo su http://127.0.0.1:8504 ---
echo --- Chiudi questa finestra per fermare il server ---
echo.
pause
endlocal
