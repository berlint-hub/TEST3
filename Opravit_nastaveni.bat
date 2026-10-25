@echo off
rem Diagnostika a oprava neukladajiciho se nastaveni (masquerade.ini)
rem ve Vampire: The Masquerade - Redemption.
rem Staci Python 3 (python.org, pri instalaci zaskrtnout "Add python.exe to PATH").
rem Kdyby oprava hlasila, ze nejde zapisovat do slozky hry,
rem pust tenhle .bat jako spravce: pravy klik -> Spustit jako spravce.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python oprava_nastaveni.py
) else (
    py oprava_nastaveni.py
)
echo.
pause
