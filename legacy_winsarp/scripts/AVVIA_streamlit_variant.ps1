# AVVIA.ps1
# Avvia WinSarp AI Hub in modo sicuro (solo localhost)
Set-Location "C:\ProgettoRAG_DEV"


# Avvia Ollama in background se non e' gia' attivo
$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollama) {
    $running = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $running) {
        Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
}


# Avvia Streamlit solo su localhost (sicuro per intranet)
python -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1
