@echo off
rem Spoustec Vampire: The Masquerade - Redemption se spravnym pracovnim
rem adresarem - hra pak uklada nastaveni (masquerade.ini) i savy
rem (SaveGames) do slozky hry, at se spousti odkudkoli.
rem
rem Dej tenhle .bat + spustit_hru.py primo do slozky hry a svuj
rem autorun/launcher nasmeruj na nej misto na Vampire.exe.
rem Kdyz Python neni, bat hru stejne spusti (jen bez pripravnych kontrol) -
rem klicove je prave to "cd /d" nize.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 goto :py
where py >nul 2>nul
if %errorlevel%==0 goto :pylauncher
goto :prima

:py
python spustit_hru.py %*
goto :konec

:pylauncher
py spustit_hru.py %*
goto :konec

:prima
if not exist SaveGames mkdir SaveGames
start "" /wait Vampire.exe %*

:konec
if errorlevel 1 pause
