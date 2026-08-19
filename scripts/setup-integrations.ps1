<#
.SYNOPSIS
    Ermes — Setup automatico integrazioni chat (Teams / Slack / Telegram).
.DESCRIPTION
    Prepara il progetto per l'esposizione pubblica e configura i webhook
    per Microsoft Teams, Slack e Telegram.

    Modalità DEV   (--Mode dev)  : usa ngrok per esporre il server locale.
    Modalità PROD  (--Mode prod) : assume un reverse proxy già configurato
                                   (Caddy / Nginx con dominio pubblico).
.PARAMETER Mode
    dev | prod   (default: dev)
.PARAMETER NgrokToken
    Il tuo auth token ngrok (opzionale in dev). Ottieni da https://dashboard.ngrok.com
.PARAMETER PublicUrl
    URL pubblico già configurato (obbligatorio in prod, opzionale in dev).
.EXAMPLE
    .\scripts\setup-integrations.ps1 -Mode dev
    .\scripts\setup-integrations.ps1 -Mode prod -PublicUrl https://ermes.azienda.it
#>

param(
    [ValidateSet("dev", "prod")]
    [string]$Mode = "dev",

    [string]$NgrokToken = "",

    [string]$PublicUrl = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $PSScriptRoot
$python = "$scriptDir\.venv\Scripts\python.exe"
$envFile = "$scriptDir\.env"

# ── Colori ──
function Write-Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERR] $msg" -ForegroundColor Red }

# ── Utility ──
function Get-EnvVar($name) {
    $val = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not $val -and (Test-Path $envFile)) {
        $line = (Get-Content $envFile | Select-String "^$name=")
        if ($line) { $val = $line.ToString().Substring($name.Length + 1).Trim('"', "'") }
    }
    return $val
}

# ═══════════════════════════════════════════════════════════════
#  1. VERIFICHE PRELIMINARI
# ═══════════════════════════════════════════════════════════════
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "║   Ermes — Setup Integrazioni Chat (Teams/Slack/Telegram) ║" -ForegroundColor DarkCyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor DarkCyan

Write-Step "Verifica ambiente"

# Python virtual env
if (-not (Test-Path $python)) {
    Write-Err "Ambiente virtuale .venv non trovato. Esegui prima lo script di setup."
    exit 1
}
Write-OK "Python virtual env trovato"

# .env
if (-not (Test-Path $envFile)) {
    Write-Warn "File .env non trovato, copio da .env.example"
    Copy-Item "$scriptDir\.env.example" $envFile
}
Write-OK "File .env: $envFile"

# ERMES_API_KEY
$apiKey = Get-EnvVar "ERMES_API_KEY"
if (-not $apiKey -or $apiKey -eq "CHANGE_ME_TO_SECURE_API_KEY") {
    Write-Warn "ERMES_API_KEY non impostata o ancora da cambiare."
    Write-Warn "Le richieste alle API saranno rifiutate finché non la configuri."
    Write-Warn "Genera una key: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
}

# Server in esecuzione?
$healthOk = $false
try { $null = curl.exe -s --max-time 3 "http://127.0.0.1:8502/health"; $healthOk = $true } catch {}
if (-not $healthOk) {
    Write-Err "Ermes non è in esecuzione su http://127.0.0.1:8502"
    Write-Err "Avvia prima il server con: .\scripts\AVVIA.bat  o  .\scripts\avvia_ermes.ps1"
    exit 1
}
Write-OK "Ermes in esecuzione su http://127.0.0.1:8502"

# ═══════════════════════════════════════════════════════════════
#  2. ESPOSIZIONE PUBBLICA
# ═══════════════════════════════════════════════════════════════
Write-Step "Esposizione pubblica (modalità: $Mode)"

if ($Mode -eq "dev") {
    # ── ngrok ──
    $ngrokExe = Get-Command "ngrok" -ErrorAction SilentlyContinue
    if (-not $ngrokExe) {
        Write-Warn "ngrok non trovato. Lo installo con winget..."
        try {
            winget install ngrok -e --accept-package-agreements 2>$null
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
            $ngrokExe = Get-Command "ngrok" -ErrorAction SilentlyContinue
        } catch {
            Write-Err "Installazione ngrok fallita. Installalo manualmente da https://ngrok.com/download"
            exit 1
        }
    }
    if (-not $ngrokExe) {
        Write-Err "ngrok non disponibile. Scaricalo da https://ngrok.com/download"
        exit 1
    }
    Write-OK "ngrok trovato: $($ngrokExe.Source)"

    # Auth token
    if ($NgrokToken) {
        & ngrok config add-authtoken $NgrokToken 2>$null | Out-Null
        Write-OK "Auth token ngrok configurato"
    } else {
        Write-Warn "Nessun NgrokToken fornito. Il tunnel avrà URL casuali."
    }

    # Avvia ngrok (in background)
    Write-Host "  Avvio tunnel ngrok su porta 8502..."
    $ngrokProc = Get-Process "ngrok" -ErrorAction SilentlyContinue
    if ($ngrokProc) {
        Write-Warn "ngrok già in esecuzione, lo riavvio"
        Stop-Process -Name "ngrok" -Force -ErrorAction SilentlyContinue
        Start-Sleep 2
    }
    Start-Process -WindowStyle Hidden -FilePath "ngrok" -ArgumentList "http 8502 --log=stdout"
    Start-Sleep 4

    # Ottieni URL dal localhost API
    $publicUrl = ""
    $retries = 0
    while (-not $publicUrl -and $retries -lt 10) {
        try {
            $tunnels = curl.exe -s http://127.0.0.1:4040/api/tunnels 2>$null
            if ($tunnels) {
                $t = $tunnels | ConvertFrom-Json
                $publicUrl = $t.tunnels[0].public_url
            }
        } catch {}
        if (-not $publicUrl) {
            Start-Sleep 2
            $retries++
        }
    }

    if (-not $publicUrl) {
        Write-Err "Impossibile ottenere l'URL pubblico da ngrok."
        Write-Err "Verifica su http://127.0.0.1:4040"
        exit 1
    }
    Write-OK "Tunnel ngrok attivo: $publicUrl"

} else {
    # ── PROD: verifica URL fornito ──
    if (-not $PublicUrl) {
        Write-Err "Modalità PROD richiede -PublicUrl (es. https://ermes.azienda.it)"
        exit 1
    }
    $publicUrl = $PublicUrl.TrimEnd("/")
    Write-OK "URL pubblico: $publicUrl"

    # Verifica raggiungibilità
    try {
        $test = curl.exe -s --max-time 5 "$publicUrl/health" 2>$null
        if (-not $test) { throw "no response" }
        Write-OK "Endpoint /health raggiungibile via $publicUrl"
    } catch {
        Write-Warn "Endpoint /health non raggiungibile su $publicUrl"
        Write-Warn "Verifica che DNS e reverse proxy siano configurati correttamente."
        $continue = Read-Host "  Continuare lo stesso? (S/n)"
        if ($continue -eq "n") { exit 1 }
    }
}

# ═══════════════════════════════════════════════════════════════
#  3. TELEGRAM — REGISTRAZIONE WEBHOOK
# ═══════════════════════════════════════════════════════════════
Write-Step "Telegram — registrazione webhook"

$telegramToken = Get-EnvVar "ERMES_TELEGRAM_BOT_TOKEN"
if (-not $telegramToken) {
    Write-Warn "ERMES_TELEGRAM_BOT_TOKEN non configurato. Salto Telegram."
    Write-Warn "  Crea un bot con @BotFather su Telegram e imposta la variabile in .env"
} else {
    $telegramWebhookUrl = "$publicUrl/api/integrations/telegram"
    Write-Host "  Registro webhook: $telegramWebhookUrl"

    try {
        $response = curl.exe -s -X POST "https://api.telegram.org/bot${telegramToken}/setWebhook" `
            -H "Content-Type: application/json" `
            -d "{\"url\": \"$telegramWebhookUrl\"}" 2>$null

        $result = $response | ConvertFrom-Json
        if ($result.ok) {
            Write-OK "Webhook Telegram registrato: $($result.description)"
        } else {
            Write-Err "Errore Telegram: $($result.description)"
        }
    } catch {
        Write-Err "Errore chiamata API Telegram: $_"
    }

    # Verifica
    try {
        $info = curl.exe -s "https://api.telegram.org/bot${telegramToken}/getWebhookInfo" 2>$null
        $whInfo = $info | ConvertFrom-Json
        if ($whInfo.ok) {
            Write-OK "Webhook attivo: $($whInfo.result.url)"
        }
    } catch {}
}

# ═══════════════════════════════════════════════════════════════
#  4. STAMPA CONFIGURAZIONE TEAMS / SLACK
# ═══════════════════════════════════════════════════════════════
Write-Step "Configurazione manuale richiesta"

Write-Host @"
╔══════════════════════════════════════════════════════════════╗
║        ISTRUZIONI PER TEAMS E SLACK                         ║
╚══════════════════════════════════════════════════════════════╝

  TEAMS — Outgoing Webhook
  ─────────────────────────────────────────────────────────
  1. Apri Microsoft Teams, vai in un canale
  2. Fai clic su "..." > "Connettori" > "Outgoing Webhook"
  3. Clicca "Aggiungi"
  4. Configura:
       Nome:      Ermes
       URL:       $publicUrl/api/integrations/teams
       Secret:    (opzionale) imposta in .env come ERMES_TEAMS_WEBHOOK_SECRET
  5. Clicca "Crea"
  6. Nel canale, scrivi @Ermes seguito dalla domanda

  SLACK — Slash Command (/ermes)
  ─────────────────────────────────────────────────────────
  1. Vai su https://api.slack.com/apps > "Create New App"
  2. Scegli "From scratch", assegna un nome e un workspace
  3. Vai su "Slash Commands" > "Create New Command"
       Comando:       /ermes
       URL richiesta: $publicUrl/api/integrations/slack
       Descrizione:   Chiedi una formula WinSarp
       Hint:          /ermes come si calcola la pausa?
  4. Salva e "Install App" nel workspace
  5. In "Basic Information" > "App Credentials" trovi:
       - Signing Secret  → impostalo come ERMES_SLACK_SIGNING_SECRET
       - Bot Token       → impostalo come ERMES_SLACK_BOT_TOKEN
  6. In Slack, scrivi /ermes nel canale per testare
"@ -ForegroundColor White

Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "Setup completato!" -ForegroundColor Green
Write-Host "  URL pubblico        : $publicUrl"
Write-Host "  Telegram            : $(if ($telegramToken) { '✓ configurato' } else { '✗ salta (manca token)' })"
if ($Mode -eq "dev") {
    Write-Host "  Dashboard ngrok     : http://127.0.0.1:4040"
}
Write-Host ""
Write-Host "Dopo aver configurato Teams e Slack, testa:"
Write-Host "  Teams     : @Ermes come si calcola la pausa?"
Write-Host "  Slack     : /ermes come si calcola la pausa?"
Write-Host "  Telegram  : invia un messaggio al bot"
Write-Host "══════════════════════════════════════════════════" -ForegroundColor DarkCyan
