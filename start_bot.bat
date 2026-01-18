@echo off
cd /d %~dp0

:: Active le venv
call .venv\Scripts\activate.bat

:: Lance le script python
python run.py --config accounts/m4rin_music/config.yml

pause
