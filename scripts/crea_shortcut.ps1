$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Ermes.lnk")
$s.TargetPath = "C:\ProgettoRAG_DEV\AVVIA_PRO.bat"
$s.IconLocation = "C:\ProgettoRAG_DEV\Ermes.ico"
$s.WorkingDirectory = "C:\ProgettoRAG_DEV"
$s.Save()
