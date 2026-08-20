# Ermes - Avvio automatico di tutti i servizi
# Usage: .\scripts\avvia_ermes.ps1

$ErrorActionPreference = "SilentlyContinue"
$scriptDir = Split-Path -Parent $PSScriptRoot
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
# L'ambiente storico `.venv` puo' provenire da un altro profilo Windows.
# Il launcher usa quello riparabile e isolato di Ermes.
$venvPython = "$scriptDir\.venv-ermes\Scripts\python.exe"
$frontendDir = "$scriptDir\frontend"

Write-Host "=== Ermes - Avvio Servizi ===" -ForegroundColor Cyan

if (-not (Test-Path $venvPython)) {
    Write-Host "Ambiente Python Ermes non trovato: $venvPython" -ForegroundColor Red
    Write-Host "Esegui: py -3.11 -m venv .venv-ermes" -ForegroundColor Yellow
    exit 1
}

try {
    & $venvPython --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Python del virtual environment non eseguibile" }
} catch {
    Write-Host "Ambiente Python Ermes non utilizzabile: $venvPython" -ForegroundColor Red
    Write-Host "Ricrealo con: py -3.11 -m venv .venv-ermes" -ForegroundColor Yellow
    Write-Host "Poi installa le dipendenze con: .\.venv-ermes\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# curl.exe is an external process: a refused/timed-out connection sets a
# non-zero exit code but does NOT raise a PowerShell exception, so a bare
# try/catch around it reports success even when the HTTP request failed.
# This function checks the actual exit code and non-empty output.
function Test-HttpUp {
    param([string]$Url, [int]$TimeoutSec = 3)
    $out = curl.exe -s --max-time $TimeoutSec $Url 2>$null
    return ($LASTEXITCODE -eq 0) -and (-not [string]::IsNullOrWhiteSpace($out))
}

# ── 1. OLLAMA ──
Write-Host "[1/4] Ollama..." -NoNewline
$ollamaOk = Test-HttpUp "http://127.0.0.1:11434/api/tags"
if (-not $ollamaOk -and (Test-Path $ollamaExe)) {
    Write-Host " avvio..." -NoNewline
    Start-Process -WindowStyle Hidden -FilePath $ollamaExe -ArgumentList "serve"
    Start-Sleep 8
    $ollamaOk = Test-HttpUp "http://127.0.0.1:11434/api/tags"
}
if ($ollamaOk) { Write-Host " OK" -ForegroundColor Green }
else { Write-Host " FALLITO" -ForegroundColor Red }

# ── 2. BACKEND ──
Write-Host "[2/4] Backend..." -NoNewline
$backendPort = 8502
$backendOk = Test-HttpUp "http://127.0.0.1:$backendPort/health"
if (-not $backendOk) {
    Write-Host " avvio su $backendPort..." -NoNewline
    Start-Process -WindowStyle Hidden -FilePath $venvPython -ArgumentList "-m uvicorn api:app --host 127.0.0.1 --port $backendPort" -WorkingDirectory $scriptDir
    # uvicorn plus model/vector-store init can take longer than a single
    # probe; poll instead of one fixed sleep.
    for ($i = 0; $i -lt 10 -and -not $backendOk; $i++) {
        Start-Sleep 2
        $backendOk = Test-HttpUp "http://127.0.0.1:$backendPort/health"
    }
}
if ($backendOk) { Write-Host " OK (porta $backendPort)" -ForegroundColor Green }
else {
    # The Vite development proxy deliberately targets 8502. Silently changing
    # backend port would create a UI that opens but cannot call the API.
    Write-Host " FALLITO: il backend non risponde su $backendPort." -ForegroundColor Red
    Write-Host " Controlla se la porta e' occupata da un altro processo, oppure avvia manualmente:" -ForegroundColor Yellow
    Write-Host " .\.venv-ermes\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port $backendPort" -ForegroundColor Yellow
    exit 1
}

# ── 3. FRONTEND ──
Write-Host "[3/4] Frontend..." -NoNewline
$frontendPort = 3000
$frontendOk = Test-HttpUp "http://127.0.0.1:$frontendPort/"
if (-not $frontendOk) {
    Write-Host " avvio..." -NoNewline
    # Start-Process -FilePath "npx" resolves to npx.ps1, and on machines
    # where .ps1 is (re)associated with a text editor instead of PowerShell,
    # this silently opens that editor instead of running Vite — no error,
    # no node process, and every subsequent curl check fails honestly
    # because nothing is actually listening. Going through cmd.exe avoids
    # the .ps1 file-association entirely and resolves npx.cmd directly.
    Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList '/c npx vite --host --config vite.config.ts' -WorkingDirectory $frontendDir
    for ($i = 0; $i -lt 6 -and -not $frontendOk; $i++) {
        Start-Sleep 2
        $frontendOk = Test-HttpUp "http://127.0.0.1:$frontendPort/"
    }
}
if ($frontendOk) { Write-Host " OK" -ForegroundColor Green }
else { Write-Host " FALLITO" -ForegroundColor Red }

# ── 4. HEALTH CHECK FINALE ──
Write-Host "[4/4] Health check finale..." -ForegroundColor Cyan
if (-not $backendOk) {
    Write-Host "  Saltato: il backend non e' mai risultato raggiungibile al passo [2/4]." -ForegroundColor Red
} else {
    try {
        $health = curl.exe -s --max-time 5 "http://127.0.0.1:$backendPort/health" 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($health)) {
            Write-Host "  Health check: nessuna risposta da /health (curl exit code $LASTEXITCODE)." -ForegroundColor Red
        } else {
            $h = $health | ConvertFrom-Json
            if ($h.status -eq "healthy") {
                Write-Host "  Sistema: HEALTHY" -ForegroundColor Green
            } else {
                Write-Host "  Sistema: $($h.status) (ollama=$($h.ollama_ok) chroma=$($h.chroma_ok))" -ForegroundColor Yellow
            }
        }
    } catch { Write-Host "  Health check non disponibile: $($_.Exception.Message)" -ForegroundColor Red }
}

Write-Host ""
Write-Host "Apertura browser su http://localhost:$frontendPort ..." -ForegroundColor Gray
Start-Process "http://localhost:$frontendPort"

Write-Host ""
Write-Host "Premi un tasto per chiudere questa finestra..." -ForegroundColor Gray
# Se siamo in modalità interattiva, attendi input; altrimenti esci subito
try {
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
} catch {
    # In modalità non interattiva, esci senza attendere
}
