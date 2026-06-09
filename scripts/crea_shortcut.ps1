# crea_shortcut.ps1
# Crea un collegamento sul Desktop per avviare AVVIA.vbs (Ermes)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$desktop = [Environment]::GetFolderPath('Desktop')
$target = Join-Path $scriptDir "AVVIA.vbs"
$working = $projectRoot
# Priorità: .ico > .svg > nessuna icona
$icon_ico = Join-Path $projectRoot "docs\assets\literature_review_reading_read_icon_179858.ico"
$icon_svg = Join-Path $projectRoot "docs\icon.svg"
$icon = if (Test-Path $icon_ico) { $icon_ico } elseif (Test-Path $icon_svg) { $icon_svg } else { $null }

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$desktop\Ermes.lnk")
$Shortcut.TargetPath = $target
$Shortcut.WorkingDirectory = $working
$Shortcut.WindowStyle = 1
$Shortcut.Description = 'Avvia Ermes - Enterprise Knowledge Hub (silenzioso)'
if ($icon) { $Shortcut.IconLocation = "$icon,0" }
$Shortcut.Save()

Write-Host "Collegamento creato sul Desktop: $desktop\Ermes.lnk"