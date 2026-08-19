$content = @'
# CREA_COLLEGAMENTO_DESKTOP.ps1
$projectPath  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$desktopPath  = [System.Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "WinSarp AI Hub.lnk"

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

$shortcut.TargetPath       = "powershell.exe"
$shortcut.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$projectPath\AVVIA.ps1`""
$shortcut.WorkingDirectory = $projectPath
$shortcut.Description      = "Avvia WinSarp AI Hub"
$shortcut.IconLocation     = "C:\Windows\System32\shell32.dll,25"
$shortcut.Save()

Write-Host "Collegamento creato sul Desktop!" -ForegroundColor Green
'@

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("C:\ProgettoRAG_DEV\CREA_COLLEGAMENTO_DESKTOP.ps1", $content, $utf8NoBom)
Write-Host "CREA_COLLEGAMENTO_DESKTOP.ps1 aggiornato OK" -ForegroundColor Green