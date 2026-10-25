@echo off
rem Rozbali soubory cestiny z Vampire1.0Full.exe do slozky Vampire1.0Full_extracted.
rem Staci mit nainstalovany Python 3 (z python.org, pri instalaci zaskrtnout
rem "Add python.exe to PATH"). Zadne dalsi knihovny nejsou potreba.
rem Tento .bat funguje v koreni repa i po prekopirovani vedle .exe a .py skriptu.
cd /d "%~dp0"

set "SKRIPT="
if exist "extract_vampire_czpatch.py" set "SKRIPT=extract_vampire_czpatch.py"
if exist "tools\extract_vampire_czpatch.py" set "SKRIPT=tools\extract_vampire_czpatch.py"
if not defined SKRIPT (
    echo Nenalezen skript extract_vampire_czpatch.py.
    echo Dej tenhle .bat do stejne slozky jako .exe a .py soubor.
    pause
    exit /b 1
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SKRIPT%"
) else (
    py "%SKRIPT%"
)

echo.
echo Hotovo. Soubory cestiny najdes ve slozce Vampire1.0Full_extracted.
pause
