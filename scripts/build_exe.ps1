# Compilatore nativo C# per Ermes.exe
# Non richiede installazione di Visual Studio (usa csc.exe integrato in Windows)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $PSScriptRoot
$cscPath = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path $cscPath)) {
    Write-Host "[ERRORE] Compilatore C# Windows non trovato in $cscPath" -ForegroundColor Red
    exit 1
}

$outputExe = Join-Path $scriptDir "Ermes.exe"
$iconPath = Join-Path $scriptDir "Ermes.ico"
$srcLauncher = Join-Path $PSScriptRoot "launcher\ErmesLauncher.cs"
$srcAssembly = Join-Path $PSScriptRoot "launcher\AssemblyInfo.cs"

Write-Host "Compilazione di Ermes.exe in corso..." -ForegroundColor Cyan

& $cscPath /target:winexe /optimize+ /out:$outputExe /win32icon:$iconPath /reference:System.dll,System.Windows.Forms.dll,System.Drawing.dll $srcLauncher $srcAssembly

if ($LASTEXITCODE -eq 0 -and (Test-Path $outputExe)) {
    Write-Host "[OK] Ermes.exe compilato con successo!" -ForegroundColor Green
    Write-Host "Percorso: $outputExe" -ForegroundColor Yellow
} else {
    Write-Host "[ERRORE] Compilazione fallita con codice $LASTEXITCODE" -ForegroundColor Red
    exit 1
}
