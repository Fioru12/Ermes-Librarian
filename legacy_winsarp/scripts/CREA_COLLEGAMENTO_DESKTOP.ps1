# Script per creare collegamento desktop con path dinamico
# Esegui questo script dalla cartella del progetto

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectPath = (Get-Item $scriptPath).FullName
$desktopPath = [System.Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "WinSarp AI Hub.lnk"
$targetPath = Join-Path $projectPath "AVVIA_FINALE.bat"

# Verifica che il target esista
if (-not (Test-Path $targetPath)) {
    Write-Host "ERRORE: AVVIA_FINALE.bat non trovato in: $projectPath" -ForegroundColor Red
    Write-Host "Assicurati di eseguire questo script dalla cartella del progetto." -ForegroundColor Yellow
    pause
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectPath
$shortcut.Description = "Avvia WinSarp AI Hub - Sistema RAG Aziendale"

# Usa icona custom se esiste, altrimenti icona di sistema
$iconPath = Join-Path $projectPath "icon.ico"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
} else {
    $shortcut.IconLocation = "C:\Windows\System32\shell32.dll,25"
}

$shortcut.Save()

Write-Host "Collegamento creato sul Desktop!" -ForegroundColor Green
Write-Host "Percorso: $shortcutPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Puoi ora avviare WinSarp AI Hub dal desktop." -ForegroundColor White
