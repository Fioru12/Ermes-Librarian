# STOP.ps1 - Arresto WinSarp AI Hub
Write-Host ""
Write-Host "=== WinSarp AI Hub - Arresto ===" -ForegroundColor Cyan

$streamlit = Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*streamlit*" -and $_.CommandLine -like "*app.py*" }
if ($streamlit) {
    Write-Host "Arresto Streamlit..." -ForegroundColor Yellow
    $streamlit | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Streamlit arrestato." -ForegroundColor Green
} else {
    Write-Host "Streamlit non in esecuzione." -ForegroundColor Gray
}

$ollama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "Arresto Ollama..." -ForegroundColor Yellow
    Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
    Write-Host "Ollama arrestato." -ForegroundColor Green
} else {
    Write-Host "Ollama non in esecuzione." -ForegroundColor Gray
}

$porta = Get-NetTCPConnection -LocalPort 8502 -ErrorAction SilentlyContinue
if ($porta) {
    Write-Host "Forzo chiusura porta 8502..." -ForegroundColor Yellow
    $porta | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Write-Host "Porta 8502 liberata." -ForegroundColor Green
} else {
    Write-Host "Porta 8502 libera." -ForegroundColor Green
}

Start-Sleep -Milliseconds 500
$check = Get-NetTCPConnection -LocalPort 8502 -ErrorAction SilentlyContinue
if ($check) {
    Write-Host "ATTENZIONE: Porta 8502 ancora occupata." -ForegroundColor Yellow
} else {
    Write-Host "Verifica finale: Porta 8502 libera." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Arresto completato ===" -ForegroundColor Cyan
Write-Host ""
Read-Host "Premi INVIO per chiudere"
