@echo off
cd /d "%~dp0"
echo ===================================================
echo   PRO AI Coach (Gemini 6v6 Battle Intelligence)
echo ===================================================
echo.
echo Starting PRO AI Coach...
echo   - Auto-detects and captures PROClient window
echo   - 6v6 Team tracking and Held Item management
echo   - Keep your in-game Battle Log OPEN during battles!
echo.
start "PRO AI Coach" /belownormal python main.py %*
exit
