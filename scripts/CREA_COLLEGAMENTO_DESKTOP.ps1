# CREA_COLLEGAMENTO_DESKTOP.ps1
# Crea un collegamento sul Desktop che avvia Ermes tramite l'unico launcher
# ufficiale, scripts\avvia_ermes.ps1.
#
# Usage: .\scripts\CREA_COLLEGAMENTO_DESKTOP.ps1

$scriptDir   = $PSScriptRoot
$projectPath = Split-Path -Parent $scriptDir
$launcher    = Join-Path $scriptDir "avvia_ermes.ps1"

if (-not (Test-Path $launcher)) {
    Write-Host "Launcher non trovato: $launcher" -ForegroundColor Red
    exit 1
}

$desktopPath  = [System.Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Ermes Knowledge.lnk"

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

$shortcut.TargetPath       = "powershell.exe"
# -WindowStyle Hidden: la finestra di PowerShell non deve restare davanti all'app.
$shortcut.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
$shortcut.WorkingDirectory = $projectPath
$shortcut.Description      = "Avvia Ermes Knowledge"
$icona = Join-Path $projectPath "Ermes.ico"
if (Test-Path -LiteralPath $icona) { $shortcut.IconLocation = "$icona,0" } else { $shortcut.IconLocation = "C:\Windows\System32\shell32.dll,25" }
$shortcut.WindowStyle      = 7  # ridotta a icona, per chi la vedesse comunque comparire
$shortcut.Save()

Write-Host "Collegamento creato sul Desktop: $shortcutPath" -ForegroundColor Green
