@echo off
cd /d %~dp0
.venv\Scripts\python.exe run_collect.py >> logs\daily.log 2>&1
