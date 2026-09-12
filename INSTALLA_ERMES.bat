@echo off
title Ermes Knowledge - Installatore Automatico
color 0B
cls

echo ==============================================================================
echo        ERMES KNOWLEDGE - INSTALLATORE AUTOMATICO ENTERPRISE
echo ==============================================================================
echo.
echo  Questo strumento preparera' l'ambiente completo sul tuo computer:
echo   1. Verifica dei prerequisiti (Python 3.11+ e Node.js)
echo   2. Creazione dell'ambiente virtuale isolato (.venv-ermes)
echo   3. Installazione automatica delle dipendenze Python
echo   4. Installazione e configurazione dell'interfaccia React
echo   5. Configurazione del file .env e credenziali di primo accesso
echo   6. Creazione icona di avvio rapido sul Desktop
echo.
echo ==============================================================================
echo.

REM 1. Verifica Python
echo [1/6] Verifica presenza di Python...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    py --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        color 0C
        echo.
        echo [ERRORE] Python non e' installato o non e' presente nel PATH di Windows!
        echo Scarica e installa Python 3.11 o 3.12 da https://www.python.org/
        echo IMPORTANTE: Ricordati di spuntare "Add Python to PATH" durante il setup.
        echo.
        pause
        exit /b 1
    )
    set "PY_CMD=py"
) else (
    set "PY_CMD=python"
)
echo      -^> Python rilevato con successo.

REM 2. Verifica Node.js
echo.
echo [2/6] Verifica presenza di Node.js e npm...
npm --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    color 0E
    echo [AVVISO] Node.js o npm non trovati nel PATH.
    echo L'interfaccia utente React richiede Node.js 18+ per essere compilata/eseguita localmente.
    echo Puoi scaricarlo da https://nodejs.org/
    echo Se intendi usare Docker, Node.js locale non e' necessario.
    echo.
) else (
    echo      -^> Node.js e npm rilevati con successo.
)

REM 3. Creazione Ambiente Virtuale Python
echo.
echo [3/6] Configurazione ambiente virtuale Python (.venv-ermes)...
if not exist ".venv-ermes" (
    echo      -^> Creazione del virtual environment in corso...
    %PY_CMD% -m venv .venv-ermes
    if %ERRORLEVEL% NEQ 0 (
        color 0C
        echo [ERRORE] Impossibile creare il virtual environment.
        pause
        exit /b 1
    )
    echo      -^> Virtual environment creato.
) else (
    echo      -^> Virtual environment .venv-ermes gia' esistente.
)

REM 4. Installazione Dipendenze Python
echo.
echo [4/6] Installazione pacchetti e librerie di Ermes...
echo      -^> Aggiornamento pip...
.\.venv-ermes\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
echo      -^> Installazione requirements.txt...
.\.venv-ermes\Scripts\pip.exe install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo [ERRORE] Si e' verificato un problema durante l'installazione dei requisiti Python.
    pause
    exit /b 1
)
echo      -^> Dipendenze Python installate con successo.

REM 5. Configurazione Frontend React
echo.
echo [5/6] Preparazione interfaccia utente Frontend...
if exist "frontend\package.json" (
    echo      -^> Installazione dipendenze frontend npm...
    call npm.cmd --prefix frontend install
    echo      -^> Compilazione bundle di produzione...
    call npm.cmd --prefix frontend run build
    echo      -^> Frontend pronto.
) else (
    echo      -^> Cartella frontend non trovata, passaggio ignorato.
)

REM 6. Configurazione Ambiente .env e Accessi
echo.
echo [6/6] Configurazione file .env e credenziali di accesso...
if not exist ".env" (
    if exist ".env.example" (
        echo      -^> Creazione file .env da .env.example...
        copy /y .env.example .env >nul
    )
)
echo      -^> Generazione credenziali sicure di primo accesso...
.\.venv-ermes\Scripts\python.exe scripts\provision_local_demo_auth.py --write

REM 7. Creazione Collegamento sul Desktop
echo.
powershell.exe -ExecutionPolicy Bypass -File "scripts\CREA_COLLEGAMENTO_DESKTOP.ps1"

color 0A
cls
echo ==============================================================================
echo           INSTALLAZIONE DI ERMES KNOWLEDGE COMPLETATA CON SUCCESSO!
echo ==============================================================================
echo.
echo  Tutti i componenti sono configurati e pronti per essere utilizzati.
echo.
echo  Come avviare Ermes:
echo   - Fai doppio clic sul file "AVVIA_ERMES.bat" in questa cartella
echo   - Oppure fai doppio clic sull'icona "Ermes Knowledge" sul Desktop
echo.
echo  Il sistema aprira' automaticamente il browser all'indirizzo:
echo   -^> http://localhost:3000
echo.
echo  Le credenziali generate sono salvate nel file "LOCAL_LOGIN.txt".
echo ==============================================================================
echo.
