#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spouštěč Vampire: The Masquerade - Redemption, který zajistí, že hra
ukládá VŠECHNO (nastavení i savy) do složky hry - bez ohledu na to,
odkud a jak se spouští (zástupce, GOG/Steam, Wine frontend/autorun...).

Proč je to potřeba (ověřeno analýzou Vampire.exe):
  * masquerade.ini si hra hledá jako <pracovní adresář>\masquerade.ini
    (GetCurrentDirectoryA na 0x4cecbf a další dvě místa),
  * savy skládá jako relativní cestu "SaveGames\SP%d\..." / "MP%d"
    (sprintf v mainSave.cpp, např. 0x428df2) - tedy taky vůči
    pracovnímu adresáři,
  * i herní data čte relativně. Jediná výjimka je texture.dat
    (ta se váže ke složce s .exe).

=> Když je pracovní adresář procesu jiný než složka hry, nastavení
   i savy skončí jinde (nebo zápis tiše selže). Tenhle spouštěč proto:
   1) najde složku hry (vedle sebe, jinak detekcí jako instalátor),
   2) připraví SaveGames\ a odemkne masquerade.ini (zruší Jen-pro-čtení,
      kdyby bránil zápisu), totéž pro soubory uvnitř SaveGames,
   3) spustí Vampire.exe s pracovním adresářem = složka hry
      (na Windows přímo, na Linuxu/macOS přes wine),
   4) počká na ukončení hry a vrátí její návratový kód.
   Argumenty za -- předá hře (např.: spustit_hru.py -- -window).

Kam s ním: zkopíruj spustit_hru.py + Spustit_Vampire.bat (případně
spustit_vampire.sh pro Wine) přímo DO složky hry a svůj autorun/launcher
nasměruj na ně místo na Vampire.exe.
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
EXE_NAME = "Vampire.exe"


def find_game_dir(explicit=None):
    cands = []
    if explicit:
        cands.append(Path(explicit))
    cands.append(BASE)
    try:
        sys.path.insert(0, str(BASE))
        import instalator_cestiny as ic
        det = ic.detect_game()
        if det:
            cands.append(Path(det))
    except Exception:
        pass
    for c in cands:
        # na Linuxu/Wine muze mit exe jiny pripad pismen
        for name in (EXE_NAME, EXE_NAME.lower(), "vampire.EXE"):
            if (c / name).is_file():
                return c, c / name
    return None, None


def clear_readonly(p):
    try:
        if p.is_file() and not (os.stat(str(p)).st_mode & stat.S_IWRITE):
            os.chmod(str(p), os.stat(str(p)).st_mode | stat.S_IWRITE)
            return True
    except OSError:
        pass
    return False


def preflight(game_dir, log=print):
    notes = []
    sg = game_dir / "SaveGames"
    try:
        if not sg.is_dir():
            sg.mkdir(parents=True)
            notes.append("vytvořena složka SaveGames")
    except OSError as e:
        log(f"VAROVÁNÍ: složku SaveGames se nepodařilo vytvořit ({e}). "
            "Zkus spouštěč jako správce, nebo hru přesuň mimo Program Files.")
    if clear_readonly(game_dir / "masquerade.ini"):
        notes.append("odemčen masquerade.ini (byl Jen pro čtení)")
    n = 0
    if sg.is_dir():
        for f in sg.rglob("*"):
            if clear_readonly(f):
                n += 1
    if n:
        notes.append(f"odemčeno {n} souborů v SaveGames (Jen pro čtení brání přepsání savů)")
    for note in notes:
        log("  - " + note)
    # zapisovatelnost slozky hry (dulezite pro Program Files)
    probe = game_dir / ".cz_write_test"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        log("VAROVÁNÍ: do složky hry nejde zapisovat - nastavení ani savy se "
            "nemusí uložit. Spusť jako správce, nebo hru přesuň mimo "
            "Program Files (třeba C:\\Games\\Vampire).")


def build_command(exe, extra_args):
    if sys.platform == "win32":
        return [str(exe)] + extra_args
    wine = shutil.which("wine") or shutil.which("wine64")
    if wine:
        return [wine, str(exe)] + extra_args
    return None


def main():
    args = sys.argv[1:]
    explicit = None
    extra = []
    if "--" in args:
        i = args.index("--")
        extra = args[i + 1:]
        args = args[:i]
    if "--hra" in args:
        i = args.index("--hra")
        if i + 1 < len(args):
            explicit = args[i + 1]

    game_dir, exe = find_game_dir(explicit)
    if game_dir is None:
        print("CHYBA: nenašel jsem Vampire.exe. Dej tento spouštěč přímo do "
              "složky hry, nebo použij --hra \"C:\\cesta\\ke\\hre\".")
        return 1

    print(f"Složka hry: {game_dir}")
    print("Příprava (SaveGames, odemčení souborů, test zápisu):")
    preflight(game_dir)

    cmd = build_command(exe, extra)
    if cmd is None:
        print("CHYBA: nenašel jsem wine. Na Linuxu hru spusť přes wine se "
              "složkou hry jako pracovním adresářem (cd do ní), nebo použij "
              "přiložený spustit_vampire.sh.")
        return 1

    print(f"Spouštím: {' '.join(cmd)}")
    print(f"Pracovní adresář (sem hra ukládá nastavení i savy): {game_dir}")
    try:
        rc = subprocess.call(cmd, cwd=str(game_dir))
    except OSError as e:
        print(f"CHYBA při spuštění hry: {e}")
        return 1
    print(f"Hra byla ukončena (kód {rc}).")
    return rc


if __name__ == "__main__":
    sys.exit(main())
