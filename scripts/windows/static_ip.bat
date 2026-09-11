@echo off
title Ermes - Imposta IP Statico
:: Richiedi admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Richiedo privilegi amministratore...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Impostazione IP statico 172.21.14.224...
echo Interfaccia: Ethernet
echo Subnet mask: 255.255.254.0 (/23)
echo Gateway:     172.21.15.196
echo DNS:         172.21.15.119, 8.8.8.8
echo.

netsh interface ip set address "Ethernet" static 172.21.14.224 255.255.254.0 172.21.15.196 1
if %errorlevel% equ 0 (
    echo [OK] IP statico impostato!
) else (
    echo [ERRORE] Impossibile impostare IP statico.
    pause
    exit /b
)

netsh interface ip set dns "Ethernet" static 172.21.15.119
netsh interface ip add dns "Ethernet" 8.8.8.8 index=2
netsh interface ip add dns "Ethernet" 1.1.1.1 index=3

echo [OK] DNS impostati.
echo.
echo IP statico configurato: 172.21.14.224
echo Il link funzionera' sempre: http://172.21.14.224:8504
echo.
pause