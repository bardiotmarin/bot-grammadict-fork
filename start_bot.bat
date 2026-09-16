@echo off
cd /d %~dp0

:: Active le venv
call .venv\Scripts\activate.bat

:: Le compte est passe en argument (il ne doit pas figurer dans le depot)
if "%~1"=="" (
    echo Usage : start_bot.bat ^<compte^>
    pause
    exit /b 1
)

:: Lance le script python
python run.py --config accounts/%~1/config.yml

pause
