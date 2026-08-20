@echo off
title Ermes - Enterprise Knowledge Hub - Installer
setlocal EnableExtensions EnableDelayedExpansion

set "VER=1.0"
set "REQUIRED_PYTHON=3.11"
set "MAIN_MODEL=qwen2.5:7b"
set "EMBED_MODEL=bge-m3"

:MENU
cls
echo ============================================
echo    Ermes v%VER% - Installer
echo ============================================
echo.
echo  Questo script installa tutto il necessario
echo  per far funzionare Ermes su questo PC.
echo.
echo  Cosa verra' installato:
echo   1. Python %REQUIRED_PYTHON%+ (se mancante)
echo   2. Ollama (motore AI locale)
echo   3. Modelli AI: %MAIN_MODEL% + %EMBED_MODEL%
echo   4. Ambiente virtuale Python con dipendenze
echo   5. Collegamento sul desktop
echo.
echo  --------------------------------------------
echo  1) Installa tutto (completo)
echo  2) Solo scarica modelli AI (se gia' installato)
echo  3) Crea solo collegamento desktop
echo  4) Esci
echo  --------------------------------------------
echo.
set /P SCELTA="Scegli [1-4]: "

if "%SCELTA%"=="1" goto FULL_INSTALL
if "%SCELTA%"=="2" goto DOWNLOAD_MODELS
if "%SCELTA%"=="3" goto CREATE_SHORTCUT
if "%SCELTA%"=="4" goto FINE
goto MENU

:FULL_INSTALL
cls
echo ============================================
echo    Installazione Completa
echo ============================================
echo.

REM ── 1. Controlla Python ───────────────────────────────────────────────────────
:CHECK_PYTHON
echo [1/6] Verifica Python...
python --version >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ❌ Python non trovato!
    echo.
    echo  Ermes necessita di Python %REQUIRED_PYTHON%+
    echo  Scarica Python da: https://www.python.org/downloads/
    echo.
    echo  Durante l'installazione di Python, spunta:
    echo    "Add Python to PATH"
    echo.
    pause
    goto MENU
)

for /f "tokens=2 delims=. " %%a in ('python --version 2^>^&1') do set PY_VER_MAJOR=%%a
if %PY_VER_MAJOR% LSS 11 (
    echo.
    echo  ⚠️ Python 3.%PY_VER_MAJOR% trovato, ma serve 3.11+.
    echo  Scarica Python 3.11+ da: https://www.python.org/downloads/
    pause
    goto MENU
)
echo         ✅ Python trovato: OK
echo.

REM ── 2. Controlla/Ollama ──────────────────────────────────────────────────────
echo [2/6] Controllo Ollama...
set "OLLAMA_PATH=%LocalAppData%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA_PATH%" (
    echo         ✅ Ollama gia' installato
) else (
    echo         ⬇️ Download Ollama in corso...
    echo         (Si aprira' una finestra di download)
    start "" "https://ollama.com/download/OllamaSetup.exe"
    echo.
    echo  ⚠️  ATTENDI il download e installa Ollama manualmente.
    echo     Poi torna qui e premi un tasto per continuare.
    echo.
    pause
    if not exist "%OLLAMA_PATH%" (
        echo.
        echo  ❌ Ollama non trovato dopo l'installazione.
        echo     Installalo manualmente da ollama.com e riavvia questo script.
        pause
        goto MENU
    )
    echo         ✅ Ollama installato
)
echo.

REM ── 3. Avvia Ollama ────────────────────────────────────────────────────────────
echo [3/6] Avvio Ollama...
start "" "%OLLAMA_PATH%"
echo         Attendere l'avvio...
set RETRY=0
:WAIT_OLLAMA
timeout /t 3 /nobreak >NUL
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >NUL 2>&1
if %ERRORLEVEL% EQU 0 (
    echo         ✅ Ollama pronto!
    goto DOWNLOAD_MODELS_STEP
)
set /a RETRY+=1
if %RETRY% GEQ 10 (
    echo  ❌ Ollama non risponde. Avvialo manualmente e riprova.
    pause
    goto MENU
)
echo         ... tentativo !RETRY!/10
goto WAIT_OLLAMA

:DOWNLOAD_MODELS_STEP
REM ── 4. Scarica modelli AI ────────────────────────────────────────────────────
echo.
echo [4/6] Download modelli AI...
echo         (circa 5 GB - solo la prima volta, potrebbe richiedere minuti)
echo.

echo         -> Download %MAIN_MODEL% (4.7 GB)...
ollama pull %MAIN_MODEL%
if %ERRORLEVEL% NEQ 0 (
    echo  ❌ Download fallito per %MAIN_MODEL%. Verifica connessione.
    pause
    goto MENU
)

echo         -> Download %EMBED_MODEL% (274 MB)...
ollama pull %EMBED_MODEL%
if %ERRORLEVEL% NEQ 0 (
    echo  ❌ Download fallito per %EMBED_MODEL%. Verifica connessione.
    pause
    goto MENU
)
echo         ✅ Modelli AI pronti!
echo.

REM ── 5. Ambiente virtuale Python ──────────────────────────────────────────────
echo [5/6] Ambiente virtuale Python...
if not exist ".venv\Scripts\python.exe" (
    echo         Creazione venv...
    python -m venv .venv
    if errorlevel 1 (
        echo  ❌ Impossibile creare il venv.
        pause
        goto MENU
    )
)
echo         Installazione dipendenze...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet 2>&1 | findstr /v "already satisfied"
if %ERRORLEVEL% NEQ 0 (
    echo  ⚠️  Alcune dipendenze potrebbero non essere state installate.
    echo     Verifica la connessione e riprova.
)
echo         ✅ Ambiente pronto!
echo.

REM ── 6. Collegamento desktop ──────────────────────────────────────────────────
echo [6/6] Collegamento sul desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Ermes.lnk');$s.TargetPath='powershell.exe';$s.Arguments='-ExecutionPolicy Bypass -File \"%~dp0avvia_ermes.ps1\"';$s.WorkingDirectory='%~dp0..';$s.Description='Avvia Ermes Knowledge';$s.IconLocation='shell32.dll,13';$s.Save()"
echo         ✅ Collegamento creato sul desktop!
echo         📌 Doppio click su "Ermes" sul desktop per avviare
echo            In alternativa: AVVIA.bat (mostra finestra dei log)
echo.

echo ============================================
echo    Installazione completata! 🎉
echo ============================================
echo.
echo  Per avviare, fai doppio click su:
echo    - Il collegamento "Ermes" sul desktop
echo    - Oppure AVVIA.bat in questa cartella
echo.
pause
goto MENU

:DOWNLOAD_MODELS
cls
echo ============================================
echo    Download Modelli AI
echo ============================================
echo.
echo  Verra' scaricato:
echo    - %MAIN_MODEL% (4.7 GB - per le risposte)
echo    - %EMBED_MODEL% (274 MB - per gli embeddings)
echo.
pause

echo.
echo -> Download %MAIN_MODEL%...
ollama pull %MAIN_MODEL%
if %ERRORLEVEL% NEQ 0 (
    echo  ❌ Download fallito.
    pause
    goto MENU
)

echo -> Download %EMBED_MODEL%...
ollama pull %EMBED_MODEL%
if %ERRORLEVEL% NEQ 0 (
    echo  ❌ Download fallito.
    pause
    goto MENU
)
echo.
echo ✅ Modelli scaricati con successo!
pause
goto MENU

:CREATE_SHORTCUT
cls
echo ============================================
echo    Creazione Collegamento Desktop
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Ermes.lnk');$s.TargetPath='powershell.exe';$s.Arguments='-ExecutionPolicy Bypass -File \"%~dp0avvia_ermes.ps1\"';$s.WorkingDirectory='%~dp0..';$s.Description='Avvia Ermes Knowledge';$s.IconLocation='shell32.dll,13';$s.Save()"
if %ERRORLEVEL% EQU 0 (
    echo  ✅ Collegamento creato sul desktop!
    echo     Doppio click su "Ermes" per avviare.
) else (
    echo  ❌ Errore nella creazione del collegamento.
)
pause
goto MENU

:FINE
cls
echo.
echo ============================================
echo    Grazie per aver usato l'installer!
echo ============================================
echo.
endlocal
exit /b 0
