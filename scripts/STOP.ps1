# STOP.ps1 - Arresto dei servizi Ermes
# Controparte di scripts\avvia_ermes.ps1: ferma cio' che quello avvia.
# Usage: .\scripts\STOP.ps1

Write-Host ""
Write-Host "=== Ermes - Arresto Servizi ===" -ForegroundColor Cyan

function Stop-Port {
    param([int]$Port, [string]$Nome)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "  $Nome (porta $Port): gia' libera." -ForegroundColor Gray
        return
    }
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 600
    # Verifica che la porta sia davvero libera invece di dichiararlo e basta.
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "  $Nome (porta $Port): ANCORA OCCUPATA." -ForegroundColor Yellow
    } else {
        Write-Host "  $Nome (porta $Port): arrestato." -ForegroundColor Green
    }
}

Stop-Port -Port 8502 -Nome "Backend"
Stop-Port -Port 3000 -Nome "Frontend"

# Ollama non viene arrestato: e' un servizio di sistema che puo' servire altre
# applicazioni. Per fermarlo esplicitamente: Stop-Process -Name ollama -Force
$ollama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "  Ollama: lasciato in esecuzione (servizio condiviso)." -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Arresto completato ===" -ForegroundColor Cyan
Write-Host ""

# Attendi solo se c'e' davvero qualcuno a premere: con stdin rediretto
# Read-Host non solleva un'eccezione, si blocca a tempo indefinito.
if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
    Read-Host "Premi INVIO per chiudere" | Out-Null
}
