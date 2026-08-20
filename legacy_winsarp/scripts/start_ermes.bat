@echo off
echo Avvio Ermes RAG System...
cd /d "C:\ProgettoRAG_DEV"
start "Ermes Backend" py api.py
cd /d "C:\ProgettoRAG_DEV\frontend"
start "Ermes Frontend" npm run dev
exit