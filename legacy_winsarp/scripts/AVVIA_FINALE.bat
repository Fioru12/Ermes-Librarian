@echo off
setlocal EnableExtensions EnableDelayedExpansion
title WinSarp AI Hub - Avvio

REM ── Safe guard: evita doppia esecuzione ─────────────────────────────────────────
set "LOCKFILE=%TEMP%\winsarp_avvio.lock"
if exist "%LOCKFILE%" (
    echo [AVVIO] WinSarp AI Hub e' gia' in fase di avvio.
    echo         Se il problema persiste cancella: %LOCKFILE%
    timeout /t 5 /nobreak >NUL
    goto FINE
)
echo. 2>"%LOCKFILE%"

cd /d "%~dp0"

REM ── Solo i modelli necessari per il funzionamento ─────────────────────────────
set "REQ_MAIN_MODEL=qwen2.5:7b"
set "REQ_EMBED_MODEL=nomic-embed-text"

echo.
echo ============================================
echo    WinSarp AI Hub - Avvio Automatico
echo ============================================
echo.

REM ── Controlla che il venv esista ─────────────────────────────────────────────
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [SETUP] Ambiente virtuale non trovato. Creazione in corso...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRORE] Impossibile creare il venv. Assicurati che Python sia nel PATH.
        pause
        goto FINE
    )

    echo [SETUP] Installazione dipendenze...
    call "%~dp0venv\Scripts\activate.bat"
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERRORE] Installazione dipendenze fallita.
        pause
        goto FINE
    )

    echo [SETUP] Ambiente pronto!
    echo.
)

REM ── Attiva il venv ────────────────────────────────────────────────────────────
call "%~dp0venv\Scripts\activate.bat"

echo [1/4] Controllo motore AI (Ollama)...

REM Test diretto API Ollama
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"

if %ERRORLEVEL%==0 (
    echo         Ollama gia' attivo. OK.
    goto CHECK_MODELS
)

echo         Ollama non attivo. Provo ad avviarlo...

if exist "%LocalAppData%\Programs\Ollama\Ollama.exe" (
    start "" "%LocalAppData%\Programs\Ollama\Ollama.exe"
) else (
    echo [ERRORE] Ollama non trovato in:
    echo          %LocalAppData%\Programs\Ollama\Ollama.exe
    echo Installa o avvia Ollama manualmente.
    pause
    goto FINE
)

echo         Attendo l'inizializzazione delle API...
set RETRY_COUNT=0

:WAIT_OLLAMA
timeout /t 3 /nobreak >NUL

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"

if %ERRORLEVEL%==0 (
    echo         Ollama pronto!
    goto CHECK_MODELS
)

set /a RETRY_COUNT+=1
if %RETRY_COUNT% GEQ 15 goto OLLAMA_ERROR
echo         Ollama non ancora pronto... (Tentativo !RETRY_COUNT!/15)
goto WAIT_OLLAMA

:OLLAMA_ERROR
echo.
echo [ERRORE] Ollama non risponde dopo 45 secondi.
echo Prova ad aprire Ollama manualmente e ripeti.
pause
goto FINE

:CHECK_MODELS
echo.
echo [2/4] Verifica modelli Ollama richiesti...

set "MISSING_MODELS="
for %%M in ("%REQ_MAIN_MODEL%" "%REQ_EMBED_MODEL%") do (
    ollama list 2>NUL | find /I "%%~M" >NUL
    if errorlevel 1 (
        if defined MISSING_MODELS (
            set "MISSING_MODELS=!MISSING_MODELS!, %%~M"
        ) else (
            set "MISSING_MODELS=%%~M"
        )
    )
)

if not defined MISSING_MODELS (
    echo         Modelli presenti. OK.
    goto START_BROWSER
)

echo         Modelli mancanti: !MISSING_MODELS!
echo         Download automatico in corso (solo la prima volta)...

for %%M in ("%REQ_MAIN_MODEL%" "%REQ_EMBED_MODEL%") do (
    ollama list 2>NUL | find /I "%%~M" >NUL
    if errorlevel 1 (
        echo         -> ollama pull %%~M
        ollama pull %%~M
        if errorlevel 1 (
            echo [ERRORE] Download fallito per %%~M
            echo Verifica connessione Internet e riprova.
            pause
            goto FINE
        )
    )
)

:START_BROWSER
echo.
echo [3/4] Avvio browser...
start "" "http://127.0.0.1:8502"

echo.
echo [4/4] Lancio interfaccia WinSarp AI...
echo         Indirizzo: http://127.0.0.1:8502
echo.
python -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1

echo.
echo [AVVIO] Programma terminato.
pause

:FINE
if exist "%LOCKFILE%" del "%LOCKFILE%" >NUL 2>&1
endlocal
exit /b 0