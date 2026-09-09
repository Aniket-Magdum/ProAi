@echo off
cd /d "%~dp0"
echo Starting PRO Instant Coach (low priority, won't lag your game)...
echo Keep the in-game Battle Log panel OPEN during battles.
start "PRO Coach" /belownormal python main.py
exit
