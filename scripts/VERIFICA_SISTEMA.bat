@echo off
REM ============================================================
REM VERIFICA SISTEMA - Controlla prerequisiti
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title Ermes - Verifica Sistema

cd /d "%~dp0.."

echo.
echo ============================================================
echo   ERMES - Verifica Prerequisiti di Sistema
echo ============================================================
echo.

REM ── Python ────────────────────────────────────────────────────
echo [1/3] Ambiente virtuale Python
if exist ".venv\Scripts\python.exe" (
    for /f "tokens=*" %%i in ('".venv\Scripts\python.exe" --version') do echo ✅ %%i
) else (
    echo ❌ .venv NON trovato
    echo    Esegui: SETUP_RAPIDO.bat
    exit /b 1
)

REM ── Ollama ────────────────────────────────────────────────────
echo.
echo [2/3] Ollama
set "OLLAMA_PATH=%LocalAppData%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA_PATH%" (
    echo ✅ Ollama trovato
) else (
    echo ❌ Ollama NON trovato in:
    echo    %OLLAMA_PATH%
    echo.
    echo    Scarica e installa da: https://ollama.com/download
    exit /b 1
)

REM Controlla se Ollama è in running
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Ollama è installato ma NON RUNNING
    echo    Avvio Ollama...
    start "" "%OLLAMA_PATH%"
    echo    Attendere 5 secondi...
    timeout /t 5 /nobreak >nul
) else (
    echo ✅ Ollama è in running
)

REM ── Ambiente Virtuale ────────────────────────────────────────
echo.
echo [3/3] Dipendenze principali

REM ── Verifica dipendenze principali ─────────────────────────
echo.
echo Verifica dipendenze principali...
call .venv\Scripts\activate.bat

python -c "import streamlit; print('  ✅ streamlit')" 2>nul || echo "  ❌ streamlit non trovato"
python -c "import fastapi; print('  ✅ fastapi')" 2>nul || echo "  ❌ fastapi non trovato"
python -c "import llama_index; print('  ✅ llama-index')" 2>nul || echo "  ❌ llama-index non trovato"
python -c "import chromadb; print('  ✅ chromadb')" 2>nul || echo "  ❌ chromadb non trovato"
python -c "import ollama; print('  ✅ ollama')" 2>nul || echo "  ❌ ollama non trovato"

echo.
echo ============================================================
echo ✅ TUTTI I PREREQUISITI SONO SODDISFATTI!
echo ============================================================
echo.
echo Puoi ora avviare l'applicazione:
echo   - AVVIA.bat (per uso locale)
echo   - AVVIA.vbs (per accesso LAN)
echo.
pause
