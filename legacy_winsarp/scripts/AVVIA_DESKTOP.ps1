# AVVIA_DESKTOP.ps1
# Launcher semplificato per WinSarp AI Hub
# Crea un collegamento sul desktop e avvia l'applicazione

param(
    [switch]$CreateShortcut,       # Crea solo il collegamento senza avviare
    [switch]$NoBrowser,            # Non aprire il browser automaticamente
    [string]$Port = "8502",        # Porta personalizzata
    [string]$Address = "127.0.0.1" # Indirizzo (0.0.0.0 per LAN)
)

$PROJECT_DIR = Split-Path -Parent $PSScriptRoot
$VENV_PYTHON = Join-Path $PROJECT_DIR "venv\Scripts\python.exe"
$APP_FILE = Join-Path $PROJECT_DIR "app.py"
$SHORTCUT_NAME = "WinSarp AI Hub.lnk"
$DESKTOP_PATH = [Environment]::GetFolderPath("Desktop")

function Write-Logo {
    Write-Host ""
    Write-Host "  ⚙️  WinSarp AI Hub" -ForegroundColor Cyan
    Write-Host "  ================" -ForegroundColor Cyan
    Write-Host "  Sistema RAG aziendale - 100% OFFline" -ForegroundColor DarkGray
    Write-Host ""
}

function Install-VenvIfMissing {
    if (-not (Test-Path $VENV_PYTHON)) {
        Write-Host "  [SETUP] Ambiente virtuale non trovato. Creazione..." -ForegroundColor Yellow
        python -m venv (Join-Path $PROJECT_DIR "venv")
        if (-not (Test-Path $VENV_PYTHON)) {
            Write-Host "  [ERRORE] Impossibile creare il venv. Python 3.11+ necessario." -ForegroundColor Red
            return $false
        }
        Write-Host "  [SETUP] Installazione dipendenze..." -ForegroundColor Yellow
        & $VENV_PYTHON -m pip install -r (Join-Path $PROJECT_DIR "requirements.txt") 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [ERRORE] Installazione dipendenze fallita." -ForegroundColor Red
            return $false
        }
        Write-Host "  [SETUP] Ambiente pronto!" -ForegroundColor Green
    }
    return $true
}

function Check-Ollama {
    Write-Host "  [1/3] Controllo motore AI (Ollama)..." -ForegroundColor White
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host "         ✅ Ollama già attivo" -ForegroundColor Green
            return $true
        }
    } catch {}

    Write-Host "         ⏳ Ollama non attivo. Avvio..." -ForegroundColor Yellow
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaPath) {
        Start-Process -FilePath $ollamaPath -WindowStyle Hidden
    } else {
        # Prova da PATH
        $ollamaPath = "ollama"
        try {
            Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        } catch {
            Write-Host "  [ERRORE] Ollama non trovato. Installalo da ollama.ai" -ForegroundColor Red
            return $false
        }
    }

    Write-Host "         Attendere..." -ForegroundColor DarkGray
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 3
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
            if ($r.StatusCode -eq 200) {
                Write-Host "         ✅ Ollama pronto!" -ForegroundColor Green
                return $true
            }
        } catch {}
        Write-Host "         ... tentativo $($i+1)/15" -ForegroundColor DarkGray
    }

    Write-Host "  [ERRORE] Ollama non risponde dopo 45 secondi." -ForegroundColor Red
    return $false
}

function Check-Models {
    param([string[]]$Models)
    Write-Host "  [2/3] Verifica modelli AI..." -ForegroundColor White
    $missing = @()
    foreach ($model in $Models) {
        $result = & "ollama" list 2>$null | Select-String -Pattern $model -SimpleMatch
        if (-not $result) {
            $missing += $model
        }
    }
    if ($missing.Count -eq 0) {
        Write-Host "         ✅ Modelli presenti" -ForegroundColor Green
        return $true
    }

    Write-Host "         ⬇️ Download modelli mancanti: $($missing -join ', ')" -ForegroundColor Yellow
    foreach ($model in $missing) {
        Write-Host "         ollama pull $model ..." -ForegroundColor DarkGray
        & "ollama" pull $model
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [ERRORE] Download fallito per $model" -ForegroundColor Red
            return $false
        }
    }
    Write-Host "         ✅ Modelli pronti!" -ForegroundColor Green
    return $true
}

function Start-App {
    param([string]$Address, [string]$Port, [switch]$NoBrowser)
    Write-Host "  [3/3] Avvio interfaccia WinSarp AI Hub..." -ForegroundColor White
    Write-Host "         Indirizzo: http://$($Address):$Port" -ForegroundColor Cyan
    Write-Host ""

    # Apri browser dopo 5 secondi (se richiesto)
    if (-not $NoBrowser) {
        $url = "http://$($Address):$Port"
        Start-Job -ScriptBlock { param($u) Start-Sleep 5; Start-Process $u } -ArgumentList $url | Out-Null
    }

    # Avvia Streamlit
    & $VENV_PYTHON -m streamlit run $APP_FILE `
        --server.port $Port `
        --server.address $Address `
        --server.headless true `
        --browser.gatherUsageStats false
}

function Create-DesktopShortcut {
    Write-Host "  [SHORTCUT] Creazione collegamento sul desktop..." -ForegroundColor White
    $shortcutPath = Join-Path $DESKTOP_PATH $SHORTCUT_NAME
    $ps1Path = Join-Path $PSScriptRoot "AVVIA_DESKTOP.ps1"

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ps1Path`""
    $shortcut.WorkingDirectory = $PROJECT_DIR
    $shortcut.Description = "Avvia WinSarp AI Hub - Sistema RAG aziendale"
    $shortcut.IconLocation = "powershell.exe,0"
    $shortcut.Save()

    Write-Host "         ✅ Collegamento creato sul desktop!" -ForegroundColor Green
    Write-Host "         Nome: $SHORTCUT_NAME" -ForegroundColor DarkGray
    return $shortcutPath
}

# ============================================================
# MAIN
# ============================================================
Clear-Host
Write-Logo

if ($CreateShortcut) {
    Create-DesktopShortcut
    Write-Host ""
    Write-Host "  Puoi ora avviare WinSarp AI Hub dal collegamento sul desktop." -ForegroundColor Green
    Start-Sleep 2
    exit 0
}

# Avvio normale
Write-Host "  Premere CTRL+C per interrompere in qualsiasi momento." -ForegroundColor DarkGray
Write-Host ""

if (-not (Install-VenvIfMissing)) {
    Read-Host "Premere INVIO per chiudere"
    exit 1
}

if (-not (Check-Ollama)) {
    Read-Host "Premere INVIO per chiudere"
    exit 1
}

if (-not (Check-Models @("qwen2.5:7b", "nomic-embed-text"))) {
    Read-Host "Premere INVIO per chiudere"
    exit 1
}

Start-App -Address $Address -Port $Port -NoBrowser:$NoBrowser

Read-Host "Premere INVIO per chiudere"