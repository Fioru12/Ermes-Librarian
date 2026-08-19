# Script di avvio per WinSarp AI Hub con path dinamico
# Esegui questo script dalla cartella del progetto

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  WinSarp AI Hub - Avvio" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Percorso di Ollama (cerca in PATH o in location standard)
$ollamaPath = Get-Command "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
}

# Avvia Ollama in background se non è già attivo
if (Test-Path $ollamaPath) {
    $process = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Host "[1/2] Avvio Ollama..." -ForegroundColor Yellow
        Start-Process $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        Write-Host "      Ollama avviato." -ForegroundColor Green
    } else {
        Write-Host "[1/2] Ollama già attivo." -ForegroundColor Green
    }
} else {
    Write-Host "[ATTENZIONE] Ollama non trovato. Avvia manualmente con 'ollama serve'" -ForegroundColor Yellow
}

Write-Host "[2/2] Avvio Streamlit..." -ForegroundColor Yellow
Write-Host "      Apri http://127.0.0.1:8502 nel browser" -ForegroundColor Cyan
Write-Host ""

# Avvia Streamlit
& python -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1