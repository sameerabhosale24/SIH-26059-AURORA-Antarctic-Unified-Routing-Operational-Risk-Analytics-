@echo off
cd /d "C:\Users\samee\Desktop\AURORA\backend"
"C:\Program Files\Python314\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 >> "%~dp0uvicorn.log" 2>&1
