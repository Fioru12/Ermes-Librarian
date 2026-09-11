@echo off
REM ============================================================
REM SETUP RAPIDO ERMES - Installa tutto in 5 minuti
REM ============================================================
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Ermes - Setup Rapido

cd /d "%~dp0.."

echo.
echo ============================================================
echo   ERMES - Enterprise Knowledge Hub - SETUP RAPIDO
echo ============================================================
echo.
echo Questo script fa TUTTO:
echo   1. Crea ambiente virtuale Python
echo   2. Installa tutte le dipendenze
echo   3. Configura file .env
echo   4. Verifica Ollama
echo   5. Testa l'applicazione
echo.
echo ============================================================
echo.

REM â”€â”€ STEP 1: Verifica Python â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo [1/5] Verifica Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo âŒ ERRORE: Python non trovato!
    echo Scarica Python 3.11+ da: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2 delims=." %%a in ('python --version 2^>^&1') do set PY_MAJOR=%%a
echo âœ… Python %PY_MAJOR% trovato

REM â”€â”€ STEP 2: Crea venv â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo [2/5] Creazione ambiente virtuale (.venv)...
if exist ".venv" (
    echo â„¹ï¸  .venv giÃ  esiste, salto creazione
) else (
    echo Creazione in corso (questo puÃ² prendere 1 minuto)...
    python -m venv .venv
    if errorlevel 1 (
        echo âŒ ERRORE: Impossibile creare venv
        pause
        exit /b 1
    )
    echo âœ… Ambiente virtuale creato
)

REM â”€â”€ STEP 3: Installa dipendenze â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo [3/5] Installazione dipendenze (puÃ² durare 3-5 minuti)...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo âŒ ERRORE: Impossibile attivare venv
    pause
    exit /b 1
)
echo Aggiornamento pip...
python -m pip install --upgrade pip setuptools wheel -q
echo Installazione packages (streamlit, llama-index, chromadb, ollama...)
pip install -r requirements-legacy.txt -q
if errorlevel 1 (
    echo âŒ ERRORE: Installazione dependencies fallita
    pause
    exit /b 1
)
echo âœ… Tutte le dipendenze installate

REM â”€â”€ STEP 4: Crea/Configura .env â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo [4/5] Configurazione file .env...
if exist ".env" (
    echo â„¹ï¸  .env giÃ  esiste, uso configurazione presente
) else (
    echo Creazione .env da .env.example...
    copy ".env.example" ".env" >nul
    echo âœ… File .env creato con configurazione default
    echo.
    echo âš ï¸  NOTA: Controlla .env e personalizza se necessario:
    echo   - ERMES_ADMIN_PASSWORD (impostata a "CHANGE_ME")
    echo   - ERMES_API_KEY (impostata a "CHANGE_ME_TO_SECURE_API_KEY")
)

REM â”€â”€ STEP 5: Verifica Ollama â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo [5/5] Verifica Ollama...
set "OLLAMA_PATH=%LocalAppData%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA_PATH%" (
    echo âœ… Ollama trovato: %OLLAMA_PATH%
    
    REM Controlla se Ã¨ in running
    curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo â„¹ï¸  Ollama non Ã¨ ancora in running
        echo Avvio Ollama...
        start "" "%OLLAMA_PATH%"
        echo â³ Attendere 5 secondi per l'avvio...
        timeout /t 5 /nobreak >nul
    ) else (
        echo âœ… Ollama Ã¨ giÃ  in running
    )
) else (
    echo âš ï¸  Ollama NON trovato in: %OLLAMA_PATH%
    echo.
    echo AZIONE RICHIESTA:
    echo 1. Scarica Ollama da: https://ollama.com/download
    echo 2. Installa Ollama (seleziona opzione standard)
    echo 3. Riavvia questo script
    echo.
    pause
    exit /b 1
)

REM â”€â”€ TEST IMPORT PYTHON â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo Verifica import moduli Python...
python -c "from config import cfg; print('âœ… config.py OK')" 2>nul
if errorlevel 1 (
    echo âŒ ERRORE: Impossibile importare config.py
    pause
    exit /b 1
)

python -c "from legacy_winsarp.core.rag_engine import init_llama_settings; print('âœ… core.rag_engine.py OK')" 2>nul
if errorlevel 1 (
    echo âš ï¸  WinSarp legacy non disponibile (normale se non e' stato attivato) - non blocca il setup
)

python -c "from legacy_winsarp.modules.winsarp import WinSarpModule; print('âœ… modules OK')" 2>nul
if errorlevel 1 (
    echo âš ï¸  WinSarp legacy non disponibile (normale se non e' stato attivato) - non blocca il setup
)

REM â”€â”€ SETUP COMPLETATO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo.
echo ============================================================
echo âœ… SETUP COMPLETATO CON SUCCESSO!
echo ============================================================
echo.
echo Prossimi step:
echo.
echo 1. AVVIA l'applicazione:
echo    .venv\Scripts\activate.bat
echo    python -m streamlit run app.py --server.port 8502
echo.
echo   OPPURE esegui semplicemente: AVVIA.bat
echo.
echo 2. Accedi a: http://localhost:8502
echo.
echo 3. Carica un documento nel pannello Admin
echo.
echo 4. Fai una domanda per testare il RAG
echo.
echo ============================================================
echo.
pause
