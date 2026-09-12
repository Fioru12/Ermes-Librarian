@echo off
chcp 65001 >nul
title Ermes Knowledge - Avvio con Docker Compose
color 0B

echo ==============================================================================
echo             🐳 AVVIO DI ERMES KNOWLEDGE CON DOCKER COMPOSE 🐳
echo ==============================================================================
echo.
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo [ERRORE] Docker non e' installato o non e' avviato!
    echo Assicurati che Docker Desktop sia in esecuzione sul tuo PC.
    echo.
    pause
    exit /b 1
)

echo Avvio dei container in corso...
docker compose up -d

if %ERRORLEVEL% EQU 0 (
    color 0A
    echo.
    echo ==============================================================================
    echo  Container avviati con successo!
    echo  Accedi a Ermes Knowledge dal tuo browser all'indirizzo:
    echo   -> http://localhost:8000
    echo ==============================================================================
    echo.
    timeout /t 3 >nul
    start http://localhost:8000
) else (
    color 0C
    echo.
    echo [ERRORE] Si e' verificato un problema durante l'avvio con Docker Compose.
    pause
)
