@echo off
REM ============================================================
REM VERIFICA SISTEMA - Controlla i prerequisiti di Ermes Knowledge
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title Ermes - Verifica Sistema

cd /d "%~dp0.."
set "PROBLEMI=0"

echo.
echo ============================================================
echo   ERMES - Verifica Prerequisiti di Sistema
echo ============================================================
echo.

REM -- Python -----------------------------------------------------
echo [1/3] Ambiente virtuale Python
REM L'ambiente deve chiamarsi .venv-ermes: e' quello che cerca
REM scripts\avvia_ermes.ps1.
if exist ".venv-ermes\Scripts\python.exe" (
    for /f "tokens=*" %%i in ('".venv-ermes\Scripts\python.exe" --version') do echo   [OK] %%i
) else (
    echo   [X] .venv-ermes NON trovato
    echo       Esegui: scripts\SETUP_INSTALL.bat
    exit /b 1
)

REM -- Ollama -----------------------------------------------------
echo.
echo [2/3] Ollama
set "OLLAMA_PATH=%LocalAppData%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA_PATH%" (
    echo   [OK] Ollama trovato
    curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo   [!] Ollama installato ma non in esecuzione. Avvio...
        start "" "%OLLAMA_PATH%"
        timeout /t 5 /nobreak >nul
    ) else (
        echo   [OK] Ollama in esecuzione
    )
) else (
    REM Ollama e' opzionale: serve solo per la ricerca semantica locale
    REM e per il profilo assistente local_ollama.
    echo   [!] Ollama non trovato ^(opzionale^): https://ollama.com/download
)

REM -- Dipendenze -------------------------------------------------
echo.
echo [3/3] Dipendenze principali
set "PY=.venv-ermes\Scripts\python.exe"

for %%M in (fastapi pydantic httpx chromadb llama_index pypdf docx dotenv filelock) do (
    "%PY%" -c "import %%M" >nul 2>&1
    if errorlevel 1 (
        echo   [X] %%M non trovato
        set /a PROBLEMI+=1
    ) else (
        echo   [OK] %%M
    )
)

echo.
echo ============================================================
if !PROBLEMI! EQU 0 (
    echo   TUTTI I PREREQUISITI SONO SODDISFATTI
    echo ============================================================
    echo.
    echo Puoi avviare l'applicazione con:
    echo   scripts\avvia_ermes.ps1
) else (
    REM La versione precedente dichiarava successo incondizionatamente,
    REM anche quando ogni singolo controllo era fallito.
    echo   !PROBLEMI! DIPENDENZE MANCANTI
    echo ============================================================
    echo.
    echo Installale con:
    echo   .venv-ermes\Scripts\python.exe -m pip install -r requirements.txt
)
echo.
pause
endlocal
