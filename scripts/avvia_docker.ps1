# avvia_docker.ps1
# Avvia Docker Desktop su Windows togliendo prima i file-socket rimasti dall'ultima volta.
#
# Perche': Docker Desktop (provato con la 4.86 su Windows 11) lascia in %LOCALAPPDATA%\Docker\run
# alcuni file-socket Unix (dockerInference, dockerEthernetVfkit, userAnalyticsOtlpHttp.sock) e
# in %LOCALAPPDATA%\docker-secrets-engine il file engine.sock. Succede anche chiudendolo nel modo
# corretto. Al riavvio non riesce a cancellarli ("The file cannot be accessed by the system") e si
# ferma con un errore. Windows non li cancella; il sottosistema Linux di Docker si'.
#
# Uso:  .\scripts\avvia_docker.ps1
# Non tocca immagini, contenitori ne' volumi.

$ErrorActionPreference = "Stop"

if (Get-Process "com.docker.backend" -ErrorAction SilentlyContinue) {
    Write-Host "Docker Desktop e' gia' acceso." -ForegroundColor Green
    exit 0
}

$run = Join-Path $env:LOCALAPPDATA "Docker\run"
$residui = @(Get-ChildItem $run -Force -ErrorAction SilentlyContinue)
if ($residui.Count -gt 0) {
    Write-Host "Tolgo $($residui.Count) file rimasti in $run ..." -ForegroundColor Gray
    # Percorso ricavato dalla cartella vera, non dal nome utente: possono essere diversi
    # (per esempio utente "Fioru" con cartella C:\Users\nikof).
    $drive = $run.Substring(0, 1).ToLower()
    $linux = "/mnt/host/$drive" + $run.Substring(2).Replace('\', '/')
    wsl --shutdown 2>$null
    wsl -d docker-desktop -e sh -c "rm -f '$linux'/*" 2>$null
    wsl --shutdown 2>$null
    $ancora = @(Get-ChildItem $run -Force -ErrorAction SilentlyContinue).Count
    if ($ancora -gt 0) {
        Write-Host "Restano $ancora file: vedi docs/RUNBOOK.md, 'Docker Desktop su Windows non parte'." -ForegroundColor Yellow
    }
}

$segreti = Join-Path $env:LOCALAPPDATA "docker-secrets-engine"
if (Test-Path $segreti) {
    # Questa cartella non e' raggiungibile dal sottosistema Linux: si rinomina (Docker ne crea una nuova).
    Rename-Item $segreti ("docker-secrets-engine.old-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}

$exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
if (-not (Test-Path $exe)) {
    Write-Host "Docker Desktop non trovato in $exe" -ForegroundColor Red
    exit 1
}
Start-Process $exe
Write-Host "Docker Desktop avviato. Attendo il motore..." -ForegroundColor Gray
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 5
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker pronto." -ForegroundColor Green
        exit 0
    }
}
Write-Host "Docker non ha risposto entro 5 minuti: controlla la finestra di Docker Desktop." -ForegroundColor Yellow
exit 1
