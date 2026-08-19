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

# ── 1. OLLAMA ──
Write-Host "[1/4] Ollama..." -NoNewline
$ollamaOk = $false
try { $null = curl.exe -s --max-time 3 http://127.0.0.1:11434/api/tags; $ollamaOk = $true } catch {}
if (-not $ollamaOk -and (Test-Path $ollamaExe)) {
    Write-Host " avvio..." -NoNewline
    Start-Process -WindowStyle Hidden -FilePath $ollamaExe -ArgumentList "serve"
    Start-Sleep 8
    try { $null = curl.exe -s --max-time 3 http://127.0.0.1:11434/api/tags; $ollamaOk = $true } catch {}
}
if ($ollamaOk) { Write-Host " OK" -ForegroundColor Green }
else { Write-Host " FALLITO" -ForegroundColor Red }

# ── 2. BACKEND ──
Write-Host "[2/4] Backend..." -NoNewline
$backendPort = 8502
$backendOk = $false
try { $null = curl.exe -s --max-time 3 "http://127.0.0.1:$backendPort/health"; $backendOk = $true } catch {}
if (-not $backendOk) {
    Write-Host " avvio su $backendPort..." -NoNewline
    Start-Process -WindowStyle Hidden -FilePath $venvPython -ArgumentList "-m uvicorn api:app --host 127.0.0.1 --port $backendPort" -WorkingDirectory $scriptDir
    Start-Sleep 5
    try { $null = curl.exe -s --max-time 3 "http://127.0.0.1:$backendPort/health"; $backendOk = $true } catch {}
}
if ($backendOk) { Write-Host " OK (porta $backendPort)" -ForegroundColor Green }
else {
    # The Vite development proxy deliberately targets 8502. Silently changing
    # backend port would create a UI that opens but cannot call the API.
    Write-Host " FALLITO: la porta $backendPort non e disponibile." -ForegroundColor Red
    Write-Host " Chiudi il processo che la usa e riprova." -ForegroundColor Yellow
    exit 1
}

# ── 3. FRONTEND ──
Write-Host "[3/4] Frontend..." -NoNewline
$frontendPort = 3000
$frontendOk = $false
try { $null = curl.exe -s --max-time 3 "http://127.0.0.1:$frontendPort/"; $frontendOk = $true } catch {}
if (-not $frontendOk) {
    Write-Host " avvio..." -NoNewline
    Start-Process -WindowStyle Hidden -FilePath "npx" -ArgumentList "vite --host --config vite.config.ts" -WorkingDirectory $frontendDir
    Start-Sleep 8
    try { $null = curl.exe -s --max-time 3 "http://127.0.0.1:$frontendPort/"; $frontendOk = $true } catch {}
}
if ($frontendOk) { Write-Host " OK" -ForegroundColor Green }
else { Write-Host " FALLITO" -ForegroundColor Red }

# ── 4. HEALTH CHECK FINALE ──
Write-Host "[4/4] Health check finale..." -ForegroundColor Cyan
try {
    $health = curl.exe -s --max-time 5 "http://127.0.0.1:$backendPort/health"
    $h = $health | ConvertFrom-Json
    if ($h.status -eq "healthy") {
        Write-Host "  Sistema: HEALTHY" -ForegroundColor Green
    } else {
        Write-Host "  Sistema: $($h.status) (ollama=$($h.ollama_ok) chroma=$($h.chroma_ok))" -ForegroundColor Yellow
    }
} catch { Write-Host "  Health check non disponibile" -ForegroundColor Red }

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
