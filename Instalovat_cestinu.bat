@echo off
rem Instalator cestiny do Vampire: The Masquerade - Redemption (Python verze).
rem Staci mit nainstalovany Python 3 (python.org, pri instalaci zaskrtnout
rem "Add python.exe to PATH"). Pak na tento soubor staci poklepat.
rem Tip: kdyby instalace hlasila, ze nejde zapisovat do slozky hry
rem (hra v Program Files), pust tenhle .bat jako spravce:
rem pravy klik -> Spustit jako spravce.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python instalator_cestiny.py
) else (
    py instalator_cestiny.py
)
if errorlevel 1 pause
