@echo off
cd /d "%~dp0"
echo Starting RePrompt server...
echo This window must stay open while using the extension.
echo.
python -m uvicorn server.main:app --host 0.0.0.0 --port 8787
pause
