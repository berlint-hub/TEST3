#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instalátor fanouškovské češtiny do Vampire: The Masquerade - Redemption
(překlad: Mrazik | diakritika, grafika: Top Games | balíček Cz Patch 1.0 Full).

Proč vznikl: původní instalátor (Vampire1.0Full.exe) hledá hru jen přes
registr HKLM\\Software\\Activision\\Vampire: The Masquerade - Redemption\\v1.0
\\INSTALLDIR. Instalace z GOGu/Steamu nebo ručně překopírovaná hra ten
klíč mít nemusí - a instalátor pak hlásí, že hra není nainstalovaná.
Tady si složku hry vybereš ručně, takže to funguje vždy.

Co dělá:
  * najde hru sám (registry vč. WOW6432Node, obvyklá místa GOG/Steam),
    nebo si složku vybereš tlačítkem Procházet,
  * před přepsáním zazálohuje původní (anglické) soubory do podsložky
    "Cestina_zaloha" uvnitř složky hry - záloha se nikdy nepřepisuje,
    ani při opakované instalaci,
  * nainstaluje 96 českých souborů (strings\\, ui\\),
  * umí češtinu zase odinstalovat (obnoví zálohu, odstraní přidané soubory).

Zdroj českých souborů hledá postupně:
  1) složku Vampire1.0Full_extracted vedle tohoto skriptu,
  2) soubor Vampire1.0Full.exe + extraktor (tools\\extract_vampire_czpatch.py
     nebo vedle skriptu) - pak si soubory sám rozbalí do dočasné složky.

Spuštění:
  Grafika:   Instalovat_cestinu.bat   (nebo: python instalator_cestiny.py)
  Konzole:   python instalator_cestiny.py --cli "C:\\cesta\\ke\\hre"
             python instalator_cestiny.py --cli-obnovit "C:\\cesta\\ke\\hre"

Vyžaduje jen Python 3 (včetně tkinter pro grafiku; bez něj funguje konzole).
"""

import hashlib
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
BACKUP_DIRNAME = "Cestina_zaloha"
MANIFEST_NAME = "manifest.json"
GAME_MARKERS = [Path("strings/game.nls"), Path("strings/game.nvo"),
                Path("strings/system.nls"), Path("strings/london.ntx")]
PATCH_TITLE = "Vampire: The Masquerade - Redemption - Čeština 1.0 Full"


# --------------------------------------------------------------------- zdroje

def find_patch_source(log=print):
    """Vrati slozku obsahujici strings\\ a ui\\ s ceskymi soubory."""
    cand = BASE / "Vampire1.0Full_extracted"
    if (cand / "strings").is_dir() and (cand / "ui").is_dir():
        log(f"Soubory češtiny: {cand}")
        return cand
    exe = BASE / "Vampire1.0Full.exe"
    tool = None
    for t in (BASE / "tools" / "extract_vampire_czpatch.py",
              BASE / "extract_vampire_czpatch.py"):
        if t.is_file():
            tool = t
            break
    if exe.is_file() and tool is not None:
        log("Rozbaluji češtinu z Vampire1.0Full.exe ...")
        import importlib.util
        import struct as _struct
        spec = importlib.util.spec_from_file_location("vamp_extr", tool)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data = exe.read_bytes()
        ov = mod.pe_overlay_offset(data)
        blob = mod.LH5(data, ov + 5).decode(_struct.unpack_from('<I', data, ov + 1)[0])
        streams = mod.parse_hk_container(blob)
        files = mod.parse_data_records(streams['DATA'])
        out = Path(tempfile.mkdtemp(prefix="vampire_cz_"))
        for winpath, content in files:
            dest = out / mod.safe_relpath(winpath)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        log(f"Rozbaleno {len(files)} souborů do dočasné složky.")
        return out
    raise FileNotFoundError(
        "Nenašel jsem soubory češtiny. Vedle instalátoru musí být buď složka "
        "Vampire1.0Full_extracted (obsahuje strings\\ a ui\\), nebo soubor "
        "Vampire1.0Full.exe společně s extraktorem extract_vampire_czpatch.py.")


def list_patch_files(src_dir):
    files = []
    for top in ("strings", "ui"):
        base = src_dir / top
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    files.append(p.relative_to(src_dir))
    return files


# ----------------------------------------------------------------- hledani hry

def is_game_dir(p):
    try:
        p = Path(p)
        return p.is_dir() and any((p / m).is_file() for m in GAME_MARKERS)
    except Exception:
        return False


def registry_candidates():
    out = []
    if sys.platform != "win32":
        return out
    try:
        import winreg
    except ImportError:
        return out
    subs = [r"Software\Activision\Vampire: The Masquerade - Redemption\v1.0",
            r"Software\WOW6432Node\Activision\Vampire: The Masquerade - Redemption\v1.0"]
    for sub in subs:
        for view in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0,
                                    winreg.KEY_READ | view) as k:
                    val, _ = winreg.QueryValueEx(k, "INSTALLDIR")
                if val and Path(val).is_dir() and str(val) not in out:
                    out.append(str(val))
            except OSError:
                pass
    return out


def path_candidates():
    guesses = [
        r"C:\GOG Games\Vampire The Masquerade - Redemption",
        r"C:\Program Files (x86)\GOG Galaxy\Games\Vampire The Masquerade - Redemption",
        r"C:\Program Files (x86)\Steam\steamapps\common\Vampire The Masquerade - Redemption",
        r"C:\Program Files\Steam\steamapps\common\Vampire The Masquerade - Redemption",
        r"C:\Program Files (x86)\Activision\Vampire - Redemption",
        r"C:\Program Files\Activision\Vampire - Redemption",
        r"D:\GOG Games\Vampire The Masquerade - Redemption",
        r"D:\Steam\steamapps\common\Vampire The Masquerade - Redemption",
    ]
    return [g for g in guesses if Path(g).is_dir()]


def detect_game():
    cands = registry_candidates() + path_candidates()
    for c in cands:
        if is_game_dir(c):
            return c
    return cands[0] if cands else ""


# ------------------------------------------------------------------ instalace

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _load_manifest(backup_dir):
    mf = backup_dir / MANIFEST_NAME
    if mf.is_file():
        try:
            return json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def check_writable(game_dir):
    try:
        fd, name = tempfile.mkstemp(dir=str(game_dir), prefix=".cztest_")
        os.close(fd)
        os.unlink(name)
    except OSError:
        raise PermissionError(
            "Do složky hry nejde zapisovat. Pokud je hra v Program Files, "
            "spusť instalátor jako správce (pravý klik na Instalovat_cestinu.bat "
            "-> Spustit jako správce).")


def install(game_dir, src_dir, log=print, progress=None):
    """Zalohuje originaly a nainstaluje cestinu. Vraci statistiku."""
    game_dir = Path(game_dir)
    check_writable(game_dir)
    backup_dir = game_dir / BACKUP_DIRNAME
    old = _load_manifest(backup_dir)
    files = list_patch_files(src_dir)
    total = len(files)
    if total == 0:
        raise FileNotFoundError("Ve zdroji nejsou žádné soubory strings\\ ani ui\\.")
    stats = {"inst": 0, "backup_new": 0, "added": 0, "errors": []}
    manifest = dict(old)
    for i, rel in enumerate(files, 1):
        src = src_dir / rel
        dest = game_dir / rel
        bak = backup_dir / rel
        try:
            existed_now = dest.is_file()
            prev = old.get(str(rel))
            existed_before = prev["existed"] if prev else existed_now
            src_sha = _sha(src)
            # Zalohuj jen cizi obsah (anglicky original). Kdyby uz ve hre lezel
            # nas vlastni cesky soubor (opakovana instalace), do zalohy nepatri.
            if existed_now and not bak.exists() and _sha(dest) != src_sha:
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(dest), str(bak))
                stats["backup_new"] += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            if not existed_before:
                stats["added"] += 1
            stats["inst"] += 1
            manifest[str(rel)] = {"existed": bool(existed_before), "sha256": src_sha}
        except OSError as e:
            stats["errors"].append(f"{rel}: {e}")
            log(f"CHYBA: {rel}: {e}")
        if progress:
            progress(i, total)
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"Hotovo: nainstalováno {stats['inst']}/{total} souborů, "
        f"nově zazálohováno {stats['backup_new']} originálů, "
        f"přidaných (předtím neexistovaly) {stats['added']}.")
    if stats["errors"]:
        log(f"Chyby: {len(stats['errors'])} (viz výpis výše).")
    return stats


def uninstall(game_dir, log=print, progress=None):
    """Obnovi originaly ze zalohy a odstrani soubory pridane cestinou."""
    game_dir = Path(game_dir)
    backup_dir = game_dir / BACKUP_DIRNAME
    if not backup_dir.is_dir():
        raise FileNotFoundError(
            "Nenašel jsem složku zálohy (Cestina_zaloha) - čeština tímto "
            "instalátorem asi nebyla instalována.")
    manifest = _load_manifest(backup_dir)
    restored = removed = missing = 0
    items = list(manifest.items())
    if not items:  # zalozni rezim: obnov vse, co v zaloze je
        items = [(str(p.relative_to(backup_dir)), {"existed": True})
                 for p in sorted(backup_dir.rglob("*"))
                 if p.is_file() and p.name != MANIFEST_NAME]
    total = len(items)
    for i, (rel, info) in enumerate(items, 1):
        dest = game_dir / rel
        bak = backup_dir / rel
        try:
            if info.get("existed"):
                if bak.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(bak), str(dest))
                    restored += 1
                else:
                    missing += 1
                    log(f"POZOR: v záloze chybí {rel}")
            else:
                if dest.is_file():
                    dest.unlink()
                    removed += 1
        except OSError as e:
            log(f"CHYBA: {rel}: {e}")
        if progress:
            progress(i, total)
    log(f"Obnoveno: vráceno {restored} originálů, odstraněno {removed} "
        f"přidaných souborů" + (f", v záloze chybělo {missing}." if missing else "."))
    log("Složku Cestina_zaloha jsem nechal na místě - můžeš ji smazat ručně.")
    return {"restored": restored, "removed": removed, "missing": missing}


# ---------------------------------------------------------------------- konzole

def run_cli(game_dir, restore=False):
    print(PATCH_TITLE)
    print(f"Složka hry: {game_dir}")
    if not Path(game_dir).is_dir():
        print("CHYBA: složka neexistuje.")
        return 1
    if restore:
        uninstall(game_dir)
        return 0
    if not is_game_dir(game_dir):
        print("VAROVÁNÍ: tohle nevypadá jako složka Vampire: Redemption "
              "(nenašel jsem strings\\game.nls).")
        if input("Přesto instalovat? [a/N] ").strip().lower() not in ("a", "ano", "y", "yes"):
            print("Zrušeno.")
            return 1
    src = find_patch_source()
    st = install(game_dir, src)
    return 0 if not st["errors"] else 1


def run_console():
    print(PATCH_TITLE)
    det = detect_game()
    if det:
        print(f"Nalezená hra: {det}")
        game = input("Stiskni Enter pro tuto složku, nebo zadej jinou cestu: ").strip().strip('"') or det
    else:
        game = input("Zadej cestu ke složce hry (kde je podsložka strings): ").strip().strip('"')
    if not game:
        return 1
    print("1) Instalovat češtinu")
    print("2) Odinstalovat češtinu (obnovit zálohu)")
    volba = input("Vyber [1/2]: ").strip()
    if volba == "2":
        uninstall(game)
        return 0
    return run_cli(game)


# -------------------------------------------------------------------------- GUI

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    q = queue.Queue()
    root = tk.Tk()
    root.title(PATCH_TITLE)
    root.geometry("720x540")
    root.minsize(620, 460)

    tk.Label(root, text="Čeština do Vampire: The Masquerade – Redemption",
             font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
    tk.Label(root, justify="left", wraplength=690,
             text="Překlad: Mrazik | diakritika, grafika: Top Games (Cz Patch 1.0 Full).\n"
                  "Instalátor zkopíruje 96 českých souborů do složky hry a původní anglické "
                  "si předtím zazálohuje do podsložky Cestina_zaloha. Češtinu jde kdykoli "
                  "zase odinstalovat.").pack(anchor="w", padx=12)

    frm = tk.Frame(root)
    frm.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(frm, text="Složka hry:").pack(side="left")
    var_dir = tk.StringVar()
    ent = tk.Entry(frm, textvariable=var_dir)
    ent.pack(side="left", fill="x", expand=True, padx=6)

    lbl_status = tk.Label(root, text="", fg="#555555")
    lbl_status.pack(anchor="w", padx=12)

    def browse():
        d = filedialog.askdirectory(title="Vyber složku hry Vampire: Redemption")
        if d:
            var_dir.set(d)
            refresh_status()

    tk.Button(frm, text="Procházet…", command=browse).pack(side="left")

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=12, pady=8)
    btn_install = tk.Button(btns, text="Instalovat češtinu", width=26)
    btn_install.pack(side="left")
    btn_uninstall = tk.Button(btns, text="Odinstalovat (obnovit zálohu)", width=30)
    btn_uninstall.pack(side="left", padx=8)

    prog = ttk.Progressbar(root, mode="determinate")
    prog.pack(fill="x", padx=12)

    logbox = tk.Text(root, height=14, wrap="word")
    logbox.pack(fill="both", expand=True, padx=12, pady=8)
    sb = tk.Scrollbar(logbox, command=logbox.yview)
    logbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")

    tk.Label(root, fg="#555555",
             text="Tip: ve hře měj nastavenou 32bit hloubku barev a 32bit textury (16bit patch nepodporuje)."
             ).pack(anchor="w", padx=12, pady=(0, 10))

    def log(msg):
        q.put(("log", str(msg)))

    def refresh_status():
        d = var_dir.get().strip()
        if not d:
            lbl_status.config(text="Hru jsem sám nenašel - vyber její složku tlačítkem Procházet.")
        elif is_game_dir(d):
            lbl_status.config(text="Vypadá to jako složka Vampire: Redemption. ✓")
        else:
            lbl_status.config(text="Pozor: tady jsem Vampire: Redemption nepoznal "
                                   "(chybí strings\\game.nls).")

    def set_busy(b):
        st = "disabled" if b else "normal"
        btn_install.config(state=st)
        btn_uninstall.config(state=st)
        ent.config(state=st)

    def worker(restore):
        try:
            d = var_dir.get().strip()
            if restore:
                uninstall(d, log=log, progress=lambda i, t: q.put(("prog", i, t)))
                q.put(("done", "Čeština byla odinstalována, hra je zpět v angličtině."))
            else:
                src = find_patch_source(log=log)
                st = install(d, src, log=log, progress=lambda i, t: q.put(("prog", i, t)))
                if st["errors"]:
                    q.put(("done", "Instalace doběhla s chybami - podrobnosti ve výpisu."))
                else:
                    q.put(("done", "Čeština je nainstalovaná. Dobrou hru, Kindrede!"))
        except Exception as e:
            q.put(("error", str(e)))

    def start(restore):
        d = var_dir.get().strip()
        if not d or not Path(d).is_dir():
            messagebox.showerror("Chyba", "Vyber prosím existující složku hry.")
            return
        if not restore and not is_game_dir(d):
            if not messagebox.askyesno(
                    "Nejistá složka",
                    "Ve vybrané složce jsem nenašel soubory Vampire: Redemption "
                    "(strings\\game.nls).\n\nOpravdu sem češtinu instalovat?"):
                return
        prog.config(value=0)
        set_busy(True)
        threading.Thread(target=worker, args=(restore,), daemon=True).start()

    btn_install.config(command=lambda: start(False))
    btn_uninstall.config(command=lambda: start(True))
    var_dir.trace_add("write", lambda *a: refresh_status())

    det = detect_game()
    if det:
        var_dir.set(det)
        log(f"Hru jsem našel sám: {det}")
    else:
        log("Hru jsem sám nenašel (v registrech ani na obvyklých místech).")
        log("Klikni na Procházet a vyber složku, kde máš Vampire: Redemption nainstalovanou.")
    refresh_status()

    def drain():
        try:
            while True:
                item = q.get_nowait()
                if item[0] == "log":
                    logbox.insert("end", item[1] + "\n")
                    logbox.see("end")
                elif item[0] == "prog":
                    prog.config(maximum=item[2], value=item[1])
                elif item[0] == "done":
                    set_busy(False)
                    messagebox.showinfo("Hotovo", item[1])
                elif item[0] == "error":
                    set_busy(False)
                    logbox.insert("end", "CHYBA: " + item[1] + "\n")
                    messagebox.showerror("Chyba", item[1])
        except queue.Empty:
            pass
        root.after(60, drain)

    root.after(60, drain)
    root.mainloop()
    return 0


# ------------------------------------------------------------------------- main

def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--cli":
        return run_cli(args[1])
    if len(args) >= 2 and args[0] == "--cli-obnovit":
        return run_cli(args[1], restore=True)
    try:
        return run_gui()
    except Exception as e:
        print(f"(Grafické rozhraní nelze spustit: {e} - přepínám na konzoli.)")
        return run_console()


if __name__ == "__main__":
    sys.exit(main())
