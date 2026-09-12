@echo off
chcp 65001 >nul
title Ermes Knowledge - Crea Collegamento Desktop
color 0B

echo Creazione icona di avvio rapido "Ermes Knowledge" sul Desktop...
powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\CREA_COLLEGAMENTO_DESKTOP.ps1"

echo.
pause
