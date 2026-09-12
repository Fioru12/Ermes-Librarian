@echo off
chcp 65001 >nul
title Ermes Knowledge - Avvio Servizi
color 0B

echo ==============================================================================
echo                🚀 AVVIO DI ERMES KNOWLEDGE IN CORSO...
echo ==============================================================================
echo.
echo Controllo dell'ambiente e avvio dei servizi in background:
echo  - Motore AI Locale (se installato)
echo  - Backend API FastAPI (porta 8502)
echo  - Frontend Web React (porta 3000)
echo.
echo Apertura automatica del browser in corso...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\avvia_ermes.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AVVISO] Se l'avvio e' fallito, esegui prima "INSTALLA_ERMES.bat".
    pause
)
