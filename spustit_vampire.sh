#!/bin/sh
# Spoustec Vampire: The Masquerade - Redemption pod Wine se spravnym
# pracovnim adresarem - hra pak uklada nastaveni (masquerade.ini)
# i savy (SaveGames) do slozky hry, at se spousti odkudkoli.
#
# Dej tenhle skript + spustit_hru.py primo do slozky hry, udelej ho
# spustitelny (chmod +x spustit_vampire.sh) a svuj autorun/launcher
# nasmeruj na nej misto na samotne "wine Vampire.exe".
# Klicove je to "cd" nize - samotne wine pracovni adresar nemeni.
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1 && [ -f spustit_hru.py ]; then
    exec python3 spustit_hru.py -- "$@"
fi

mkdir -p SaveGames
WINE="$(command -v wine || command -v wine64)"
if [ -z "$WINE" ]; then
    echo "Nenasel jsem wine v PATH." >&2
    exit 1
fi
exec "$WINE" Vampire.exe "$@"
