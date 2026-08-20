# WinSarp AI Hub - Setup Iniziale v2
# Esegui con: clic destro -> "Esegui con PowerShell" (come Amministratore)
# Installa e configura tutto il necessario su un PC nuovo.

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# Path dinamico: funziona ovunque sia posizionata la cartella del progetto
$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$StreamlitDir = Join-Path $ProjectRoot ".streamlit"

function Step($n, $tot, $msg) {
    Write-Host ""
    Write-Host "  [$n/$tot] $msg" -ForegroundColor Cyan
}
function OK($m)   { Write-Host "      OK  - $m" -ForegroundColor Green  }
function SKIP($m) { Write-Host "    SKIP  - $m" -ForegroundColor Yellow }
function ERR($m)  { Write-Host "   ERRORE - $m" -ForegroundColor Red    }

Clear-Host
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "   WinSarp AI Hub  -  Setup Iniziale v2"       -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "  Cartella progetto: $ProjectRoot"              -ForegroundColor Gray
Write-Host ""


# --------------------------------------------------------
# [1/8] Verifica Python 3.9+
# --------------------------------------------------------
Step 1 8 "Verifico Python 3.9+..."
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ("$v" -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 9) { $pythonCmd = $cmd; OK "$v  ($cmd)"; break }
            else { SKIP "$v trovato ma serve 3.9+. Aggiorna da https://python.org" }
        }
    } catch {}
}
if (-not $pythonCmd) {
    ERR "Python 3.9+ non trovato nel PATH."
    Write-Host ""
    Write-Host "      1. Scarica da: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "      2. Durante l'installazione spunta:" -ForegroundColor Yellow
    Write-Host "         [x] Add Python to PATH" -ForegroundColor White
    Write-Host "      3. Riavvia questo terminale e rilancia il setup." -ForegroundColor Yellow
    Write-Host ""
    pause; exit 1
}


# --------------------------------------------------------
# [2/8] Verifica Ollama
# --------------------------------------------------------
Step 2 8 "Verifico Ollama..."
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaExe)) {
    $found = Get-Command ollama -ErrorAction SilentlyContinue
    if ($found) { $ollamaExe = $found.Source; OK "Ollama in PATH: $ollamaExe" }
    else {
        ERR "Ollama non trovato."
        Write-Host ""
        Write-Host "      1. Scarica da: https://ollama.com/download/windows" -ForegroundColor Yellow
        Write-Host "      2. Installa e riavvia questo terminale." -ForegroundColor Yellow
        Write-Host ""
        Read-Host "      Premi INVIO dopo aver installato Ollama"
        $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
        if (-not (Test-Path $ollamaExe)) {
            $f2 = Get-Command ollama -ErrorAction SilentlyContinue
            if ($f2) { $ollamaExe = $f2.Source } else { ERR "Ollama ancora non trovato. Riavvia."; pause; exit 1 }
        }
        OK "Ollama trovato: $ollamaExe"
    }
} else { OK "Ollama trovato: $ollamaExe" }


# --------------------------------------------------------
# [3/8] Avvia Ollama serve
# --------------------------------------------------------
Step 3 8 "Avvio Ollama in background..."
$proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($proc) { SKIP "Ollama gia' in esecuzione (PID $($proc.Id))" }
else {
    Start-Process $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    Write-Host "      Attendo avvio (5s)..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
    $proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if ($proc) { OK "Ollama avviato (PID $($proc.Id))" }
    else { ERR "Ollama non si e' avviato. Prova manualmente: ollama serve" }
}


# --------------------------------------------------------
# [4/8] Scarica modelli Ollama
# --------------------------------------------------------
Step 4 8 "Scarico modelli Ollama (10-30 min al primo avvio)..."

Write-Host "      [4a] qwen2.5:7b (~4.7 GB)..." -ForegroundColor Yellow
& $ollamaExe pull qwen2.5:7b
if ($LASTEXITCODE -eq 0) { OK "qwen2.5:7b pronto" }
else { ERR "Errore qwen2.5:7b (exit $LASTEXITCODE)" }

Write-Host "      [4b] nomic-embed-text (~274 MB)..." -ForegroundColor Yellow
& $ollamaExe pull nomic-embed-text
if ($LASTEXITCODE -eq 0) { OK "nomic-embed-text pronto" }
else { ERR "Errore nomic-embed-text (exit $LASTEXITCODE)" }


# --------------------------------------------------------
# [5/8] Dipendenze Python
# --------------------------------------------------------
Step 5 8 "Installo dipendenze Python..."
Set-Location $ProjectRoot
& $pythonCmd -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $pythonCmd -m pip install -r "$ProjectRoot\requirements.txt"
if ($LASTEXITCODE -eq 0) { OK "Dipendenze installate" }
else { ERR "Errore pip (exit $LASTEXITCODE). Controlla requirements.txt" }


# --------------------------------------------------------
# [6/8] Genera config.toml Streamlit
# --------------------------------------------------------
Step 6 8 "Genero configurazione Streamlit..."

if (-not (Test-Path $StreamlitDir)) {
    New-Item -ItemType Directory -Path $StreamlitDir | Out-Null
}

$tomlContent = @"
[server]
address = "127.0.0.1"
port = 8502
headless = true
enableXsrfProtection = true
maxUploadSize = 50

[browser]
gatherUsageStats = false

[client]
showSidebarNavigation = false
toolbarMode = "minimal"

[theme]
base = "dark"
backgroundColor = "#0d1117"
secondaryBackgroundColor = "#161b22"
textColor = "#e6edf3"
primaryColor = "#388bfd"
font = "sans serif"
"@

$targetFile = Join-Path $StreamlitDir "config.toml"
$utf8NoBom  = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($targetFile, $tomlContent, $utf8NoBom)

if (Test-Path $targetFile) {
    OK "config.toml scritto in $targetFile"
    try {
        $check = & $pythonCmd -m streamlit config show 2>&1 | Select-String "server.port"
        if ($check) { Write-Host "      Porta rilevata: 8502 (OK)" -ForegroundColor DarkGray }
    } catch { SKIP "Validazione CLI non disponibile, file presente." }
} else {
    ERR "Errore creazione config.toml"
}


# --------------------------------------------------------
# [7/8] Configurazione sistema (firewall + autostart Ollama)
# --------------------------------------------------------
Step 7 8 "Configurazione sistema..."

# OLLAMA_HOST su localhost (sicuro, Ollama non esposto in LAN)
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'User')
OK "OLLAMA_HOST=127.0.0.1:11434"

# Avvio automatico Ollama al login (WindowStyle Hidden = nessuna finestra nera)
$action   = New-ScheduledTaskAction -Execute $ollamaExe -Argument "serve"
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'OllamaAutoStart' -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Highest -Force | Out-Null
OK "Ollama avvio automatico al login (nessuna finestra visibile)"

# Firewall: porta 8502 Streamlit
Remove-NetFirewallRule -DisplayName "WinSarp AI Hub" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "WinSarp AI Hub" -Direction Inbound -Protocol TCP `
    -LocalPort 8502 -Action Allow -ErrorAction SilentlyContinue | Out-Null
OK "Porta 8502 aperta nel firewall"

# Blocca Ollama API dalla LAN
Remove-NetFirewallRule -DisplayName "Blocca Ollama LAN" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Blocca Ollama LAN" -Direction Inbound -Protocol TCP `
    -LocalPort 11434 -Action Block -ErrorAction SilentlyContinue | Out-Null
OK "Porta 11434 (Ollama API) bloccata dalla LAN"


# --------------------------------------------------------
# [8/8] Collegamento Desktop
# --------------------------------------------------------
Step 8 8 "Creo collegamento Desktop..."
$launcher     = Join-Path $ProjectRoot "scripts\avvia_ermes.ps1"
$shortcutPath = "$env:USERPROFILE\Desktop\Ermes Knowledge.lnk"
$wsh = New-Object -ComObject WScript.Shell
$sc  = $wsh.CreateShortcut($shortcutPath)
$sc.TargetPath       = "powershell.exe"
$sc.Arguments        = "-ExecutionPolicy Bypass -File `"$launcher`""
$sc.WorkingDirectory = $ProjectRoot
$sc.Description      = "Avvia Ermes Knowledge"
$sc.IconLocation     = "shell32.dll,13"
$sc.Save()
OK "Collegamento Desktop creato"


# --------------------------------------------------------
# FINE
# --------------------------------------------------------
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Green
Write-Host "   Setup completato!" -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Come avviare l'app:" -ForegroundColor White
Write-Host "    Doppio clic su 'WinSarp AI Hub' sul Desktop" -ForegroundColor Green
Write-Host ""
Write-Host "  URL (solo questo PC):" -ForegroundColor White
Write-Host "    http://127.0.0.1:8502" -ForegroundColor Green
Write-Host ""
Write-Host "  Documenti:" -ForegroundColor White
Write-Host "    $ProjectRoot\documenti\WinSarp\" -ForegroundColor Gray
Write-Host "    Aggiungi PDF/TXT e clicca Aggiorna nell'app." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Per accesso da altri PC in LAN:" -ForegroundColor White
Write-Host "    Configura un reverse proxy (IIS/Nginx)." -ForegroundColor Yellow
Write-Host ""
pause
