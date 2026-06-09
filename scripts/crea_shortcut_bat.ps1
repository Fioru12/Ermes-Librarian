$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desktop = [Environment]::GetFolderPath('Desktop')
$target = Join-Path $projectRoot "scripts\AVVIA.vbs"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$desktop\Ermes.lnk")
$Shortcut.TargetPath = $target
$Shortcut.WorkingDirectory = $projectRoot
$Shortcut.WindowStyle = 1
$Shortcut.Description = 'Avvia Ermes - Enterprise Knowledge Hub'
$Shortcut.Save()

Write-Host "Collegamento ricreato: $desktop\Ermes.lnk -> $target"
