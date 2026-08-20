@echo off
title Ermes Server - Chiudi per arrestare
cd /d "%~dp0"
echo Avvio Ermes su http://localhost:8504
echo Chiudi questa finestra per arrestare il server.
start http://localhost:8504
set ERMES_PORT=8504
".venv\Scripts\python.exe" -m uvicorn api:app --host 0.0.0.0 --port 8504
