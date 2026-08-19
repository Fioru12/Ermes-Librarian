@echo off
title WinSarp AI Hub - Avvio
:: Entra nella cartella scripts e poi sale alla root
cd /d "%~dp0"
cd ..

echo.
echo  ============================================
echo     WinSarp AI Hub - Avvio Automatico
echo  ============================================
echo.

:: --- 1. CONTROLLO OLLAMA ---
echo [1/3] Controllo motore AI (Ollama)...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if %ERRORLEVEL%==0 (
    echo        Ollama gia' in esecuzione. OK.
    goto CHECK_MODEL
)

echo        Ollama non attivo. Lo avvio...
start "" "ollama" serve
echo        Attendo l'inizializzazione delle API...
timeout /t 5 /nobreak >NUL

:: Inizializzo il contatore fuori da ogni blocco
set RETRY_COUNT=0

:WAIT_OLLAMA
curl -s http://localhost:11434 >NUL 2>&1
if %ERRORLEVEL%==0 (
    echo        Ollama pronto!
    goto CHECK_MODEL
)

set /a RETRY_COUNT=%RETRY_COUNT%+1

:: Se abbiamo superato i 6 tentativi (30 secondi), ci fermiamo
if %RETRY_COUNT% GEQ 6 goto OLLAMA_ERROR

echo        Ollama non ancora pronto... (Tentativo %RETRY_COUNT%/6)
timeout /t 5 /nobreak >NUL
goto WAIT_OLLAMA

:OLLAMA_ERROR
echo.
echo  [ERRORE] Ollama non risponde dopo 30 secondi.
echo  Assicurati che Ollama sia installato e funzionante.
pause
exit /b 1

:CHECK_MODEL
:: --- 2. VERIFICA MODELLO ---
echo.
echo [2/3] Verifico presenza modello qwen2.5:7b...
ollama list 2>NUL | find "qwen2.5:7b" >NUL
if %ERRORLEVEL%==0 (
    echo        Modello presente. OK.
) else (
    echo        Modello non trovato. Download in corso...
    ollama pull qwen2.5:7b
    if %ERRORLEVEL% NEQ 0 (
        echo  [ERRORE] Download fallito. Controlla la connessione.
        pause
        exit /b 1
    )
)

:: --- 3. AVVIO STREAMLIT E BROWSER ---
echo.
echo [3/3] Lancio interfaccia WinSarp AI...
echo        Indirizzo: http://localhost:8502
echo.

:: Avvio del browser "nascosto" per evitare il secondo terminale
powershell -WindowStyle Hidden -Command "Start-Sleep 5; Start-Process 'http://localhost:8502'"

:: Esecuzione con percorso assoluto Python 3.14
"C:\Users\n.fiorucci\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m streamlit run app.py --server.port 8502 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false

pause