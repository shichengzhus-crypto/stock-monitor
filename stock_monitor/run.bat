@echo off
set DEEPSEEK_API_KEY=sk-1ac5f66c433f4f20b271b054433da6c5
cd /d D:\AI_claude_code\stock_monitor
python main.py >> logs\run.log 2>&1
