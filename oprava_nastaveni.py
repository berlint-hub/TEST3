#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostika a oprava neukládajícího se nastavení ve Vampire: The Masquerade
- Redemption (masquerade.ini).

Co jsme zjistili přímo z Vampire.exe:
  * hra si cestu k ini staví jako <pracovní adresář procesu>\\masquerade.ini
    (GetCurrentDirectory + spojení cesty, pak Get/WritePrivateProfile*),
  * EXE nemá manifest -> na Windows Vista a novějších pro ni platí UAC
    virtualizace souborů.

Z toho plynou tři typické příčiny "nastavení se neuloží / po restartu je
všechno v základu" (a správce na ně nemusí pomoct):

  1) masquerade.ini má atribut Jen pro čtení. Zápis tiše selže - i správci,
     protože atribut blokuje otevření souboru pro zápis.
  2) Existují DVĚ kopie ini: pravá ve složce hry a virtualizovaná v
     %LOCALAPPDATA%\\VirtualStore\\... Běh bez správce čte/píše virtuální,
     běh jako správce pravou. Střídání = nastavení se "ztrácí".
  3) Hra se spouští s jiným pracovním adresářem (prázdné pole "Spustit v"
     u zástupce), takže ini vzniká/hledá se jinde než ve složce hry.

Tento nástroj všechny kopie najde, ukáže jejich obsah a časy změn
a nabídne bezpečné opravy: zrušení Jen-pro-čtení, sjednocení kopií
(novější přepíše starší, VirtualStore kopie se pak smaže) a volitelně
ruční nastavení rozlišení/hloubky + zamčení souboru proti přepisu.

Použití:
  Opravit_nastaveni.bat                      (dvojklik, interaktivní)
  python oprava_nastaveni.py                 (dtto)
  python oprava_nastaveni.py --hra "C:\\cesta\\ke\\hre" --jen-diagnostika
  python oprava_nastaveni.py --hra "..." --opravit
  python oprava_nastaveni.py --hra "..." --nastav 1920x1080x32 [--zamknout]
"""

import argparse
import datetime
import os
import shutil
import stat
import sys
from pathlib import Path, PureWindowsPath

BASE = Path(__file__).resolve().parent
INI_NAME = "masquerade.ini"
DISPLAY_KEYS = ("screenWidth", "screenHeight", "screenDepth")


# ------------------------------------------------------------- hledani hry

def detect_game():
    try:
        sys.path.insert(0, str(BASE))
        import instalator_cestiny as ic  # vedle lezici instalator cestiny
        return ic.detect_game()
    except Exception:
        return ""


def game_markers_ok(p):
    p = Path(p)
    return p.is_dir() and ((p / "Local_Eng.nob").is_file()
                            or (p / "vampire.exe").is_file()
                            or (p / "strings" / "game.nls").is_file())


# ------------------------------------------------------------- VirtualStore

def virtualstore_path(win_ini_path, localappdata=None):
    """Cesta, kam UAC virtualizace presmeruje zapis do chranene slozky."""
    la = localappdata or os.environ.get("LOCALAPPDATA", "")
    if not la:
        return None
    rel = PureWindowsPath(win_ini_path).drive
    p = PureWindowsPath(win_ini_path)
    parts = p.parts[1:] if rel else p.parts  # bez pismena disku
    return Path(str(PureWindowsPath(la) / "VirtualStore" / PureWindowsPath(*parts)))


def ini_candidates(game_dir):
    game_dir = Path(game_dir)
    cands = [game_dir / INI_NAME]
    vs = virtualstore_path(str(game_dir / INI_NAME))
    if vs is not None and vs not in cands:
        cands.append(vs)
    # ini mohlo vzniknout i v pracovnim adresari, odkud se hra spousti
    cwd_ini = Path.cwd() / INI_NAME
    if cwd_ini not in cands:
        cands.append(cwd_ini)
    return cands


# ------------------------------------------------------------- prace s ini

def parse_ini(text):
    """Velmi jednoduchy parser: {(sekce_lower): {klic_lower: hodnota}}."""
    out = {}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            out.setdefault(section, {})
        elif "=" in line and section is not None:
            k, v = line.split("=", 1)
            out[section][k.strip().lower()] = v.strip()
    return out


def ini_set(text, section, values):
    """Nastavi klice v sekci, ostatni radky necha beze zmeny. Vraci novy text."""
    lines = text.splitlines()
    sec_lower = section.lower()
    todo = dict(values)
    in_sec = False
    sec_end = None
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            if in_sec and sec_end is None:
                sec_end = i
            in_sec = (line[1:-1].strip().lower() == sec_lower)
            continue
        if in_sec and "=" in line:
            k = line.split("=", 1)[0].strip()
            for key in list(todo):
                if k.lower() == key.lower():
                    lines[i] = f"{key}={todo.pop(key)}"
    if todo:
        new_lines = [f"{k}={v}" for k, v in todo.items()]
        if sec_end is not None:
            lines[sec_end:sec_end] = new_lines
        elif in_sec:
            lines.extend(new_lines)
        else:
            lines.append(f"[{section}]")
            lines.extend(new_lines)
    return "\r\n".join(lines) + "\r\n"


def is_readonly(p):
    return not (os.stat(str(p)).st_mode & stat.S_IWRITE)


def clear_readonly(p):
    os.chmod(str(p), os.stat(str(p)).st_mode | stat.S_IWRITE)


def set_readonly(p):
    os.chmod(str(p), os.stat(str(p)).st_mode & ~stat.S_IWRITE)


def describe(p):
    p = Path(p)
    if not p.is_file():
        return f"  {p}\n    neexistuje"
    st = p.stat()
    when = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
    vals = {}
    try:
        parsed = parse_ini(p.read_text(encoding="cp1250", errors="replace"))
        for sec in ("render", "gameoptions"):
            for k in DISPLAY_KEYS:
                if k.lower() in parsed.get(sec, {}):
                    vals[k] = parsed[sec][k.lower()]
        secs = ", ".join(sorted(parsed)) or "?"
    except OSError as e:
        secs = f"(nejde přečíst: {e})"
    ro = "  << JEN PRO ČTENÍ - hra do něj nezapíše!" if is_readonly(p) else ""
    disp = " ".join(f"{k}={vals.get(k, '?')}" for k in DISPLAY_KEYS)
    return (f"  {p}\n    existuje, {st.st_size} B, změněno {when}{ro}\n"
            f"    zobrazení: {disp}\n    sekce: {secs}")


# ------------------------------------------------------------- opravy

def fix_readonly(paths, log=print):
    n = 0
    for p in paths:
        if Path(p).is_file() and is_readonly(p):
            try:
                clear_readonly(p)
                log(f"  zrušen atribut Jen pro čtení: {p}")
                n += 1
            except OSError as e:
                log(f"  CHYBA při rušení Jen pro čtení ({p}): {e}")
    return n


def unify(game_ini, vs_ini, log=print):
    """Sjednoti pravou a VirtualStore kopii (vyhraje novejsi), VS smaze."""
    game_ini, vs_ini = Path(game_ini), Path(vs_ini)
    if not vs_ini.is_file():
        return False
    if game_ini.is_file() and game_ini.stat().st_mtime >= vs_ini.stat().st_mtime:
        log("  kopie ve složce hry je novější - nechávám ji, VirtualStore mažu")
    else:
        if game_ini.is_file() and is_readonly(game_ini):
            clear_readonly(game_ini)
        shutil.copy2(str(vs_ini), str(game_ini))
        log("  VirtualStore kopie byla novější - zkopírována do složky hry")
    try:
        vs_ini.unlink()
        log(f"  smazána VirtualStore kopie: {vs_ini}")
    except OSError as e:
        log(f"  CHYBA při mazání VirtualStore kopie: {e}")
        return False
    return True


def apply_settings(ini_path, width, height, depth, lock=False, log=print):
    p = Path(ini_path)
    if not p.is_file():
        log(f"  {p} neexistuje - vytvářím nový s požadovaným nastavením")
        text = ""
    else:
        if is_readonly(p):
            clear_readonly(p)
        text = p.read_text(encoding="cp1250", errors="replace")
    text = ini_set(text, "render", {"screenWidth": width,
                                    "screenHeight": height,
                                    "screenDepth": depth})
    p.write_text(text, encoding="cp1250")
    log(f"  nastaveno screenWidth={width} screenHeight={height} screenDepth={depth}: {p}")
    if lock:
        set_readonly(p)
        log("  soubor zamčen (Jen pro čtení) - hra si ho nepřepíše; pro další "
            "změny nastavení ve hře ho zase odemkni (Vlastnosti souboru).")


def in_protected_dir(p):
    s = str(p).lower()
    return ("program files" in s) or s.startswith("c:\\windows")


# ------------------------------------------------------------- prubeh

def diagnose(game_dir, log=print):
    cands = ini_candidates(game_dir)
    log(f"Složka hry: {game_dir}")
    log("Kandidáti na masquerade.ini (hra používá <pracovní adresář>\\masquerade.ini):")
    for c in cands:
        log(describe(c))
    return cands


def advice(game_dir, cands, log=print):
    game_ini = Path(game_dir) / INI_NAME
    vs = cands[1] if len(cands) > 1 else None
    log("")
    log("Co z toho plyne:")
    if game_ini.is_file() and is_readonly(game_ini):
        log("  * INI VE SLOŽCE HRY JE JEN PRO ČTENÍ - to je nejpravděpodobnější "
            "příčina. Hra zápis ani nezkusí ohlásit, nastavení se ztratí.")
    if vs is not None and Path(vs).is_file():
        log("  * EXISTUJE I VIRTUALSTORE KOPIE - běh bez správce používá ji, "
            "běh jako správce tu pravou. Proto 'správce nepomohl': každá "
            "varianta koukala do jiného souboru.")
    if in_protected_dir(game_dir):
        log("  * Hra je v chráněné složce (Program Files). Nejjistější je hru "
            "přesunout mimo ni (např. C:\\Games\\Vampire) - virtualizace tím "
            "odpadne. Jinak spouštěj hru POŘÁD stejně (ideálně vždy jako správce).")
    log("  * Zkontroluj zástupce hry: pole 'Spustit v' má být složka hry - "
        "hra hledá ini v pracovním adresáři, ne u .exe.")
    log("  * Hru ukončuj přes Quit v menu, ne natvrdo (Alt+F4 / Správce úloh) - "
        "nastavení se zapisuje při řádném ukončení/uložení voleb.")


def main():
    ap = argparse.ArgumentParser(description="Diagnostika/oprava ukládání nastavení (masquerade.ini)")
    ap.add_argument("--hra", help="složka hry (jinak se zkusí najít sama / zeptám se)")
    ap.add_argument("--jen-diagnostika", action="store_true", help="nic neměnit, jen vypsat stav")
    ap.add_argument("--opravit", action="store_true",
                    help="proveď bezpečné opravy (Jen-pro-čtení, sjednocení kopií)")
    ap.add_argument("--nastav", metavar="SxVxH", help="nastav rozlišení a hloubku, např. 1920x1080x32")
    ap.add_argument("--zamknout", action="store_true",
                    help="po nastavení soubor zamkni (Jen pro čtení), ať ho hra nepřepíše")
    a = ap.parse_args()

    print("Vampire: The Masquerade - Redemption - oprava ukládání nastavení")
    print("=" * 68)
    game = a.hra or detect_game()
    if not game:
        game = input("Zadej cestu ke složce hry: ").strip().strip('"')
    if not game or not Path(game).is_dir():
        print("CHYBA: složka hry neexistuje.")
        return 1
    if not game_markers_ok(game):
        print("VAROVÁNÍ: ve složce jsem Vampire: Redemption nepoznal "
              "(chybí Local_Eng.nob / vampire.exe / strings\\game.nls).")
        if not a.opravit and not a.jen_diagnostika and not a.nastav:
            if input("Pokračovat přesto? [a/N] ").strip().lower() not in ("a", "ano"):
                return 1

    cands = diagnose(game)
    advice(game, cands)
    game_ini = Path(game) / INI_NAME
    vs_ini = cands[1] if len(cands) > 1 else None

    if a.jen_diagnostika:
        return 0

    do_fix = a.opravit
    if not do_fix and not a.nastav:
        ans = input("\nProvést bezpečné opravy (zrušit Jen-pro-čtení, sjednotit kopie)? [A/n] ")
        do_fix = ans.strip().lower() not in ("n", "ne", "no")
    if do_fix:
        print("\nOpravy:")
        fix_readonly([c for c in cands if Path(c).is_file()])
        if vs_ini is not None and Path(vs_ini).is_file():
            unify(game_ini, vs_ini)

    if a.nastav:
        try:
            w, h, dpth = (int(x) for x in a.nastav.lower().split("x"))
        except ValueError:
            print("CHYBA: --nastav čeká tvar např. 1920x1080x32")
            return 1
        print("\nNastavuji zobrazení:")
        apply_settings(game_ini, w, h, dpth, lock=a.zamknout)
        if vs_ini is not None and Path(vs_ini).is_file():
            apply_settings(vs_ini, w, h, dpth, lock=a.zamknout)

    print("\nHotovo. Spusť hru, změň něco v nastavení, řádně ji ukonči přes "
          "Quit a znovu zapni - nastavení musí zůstat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
