@echo off
title Ermes - Firewall
:: Richiedi permessi amministratore
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Richiedo privilegi amministratore...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Aggiungo regola firewall per porta 8504...
netsh advfirewall firewall add rule name="Ermes 8504" dir=in action=allow protocol=TCP localport=8504
if %errorlevel% equ 0 ( echo FATTO! ) else ( echo ERRORE! )

pause