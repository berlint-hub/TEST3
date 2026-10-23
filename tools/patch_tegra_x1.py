#!/usr/bin/env python3
"""
patch_tegra_x1.py — binarni patch libemucore.so pro Nintendo Switch (Nvidia Tegra X1).

ZDROJ PATCHU
------------
Patchy NEJSOU vymyslene. Jsou prevzaty z upstream projektu
<https://github.com/mininxd/NetherSX2-patch>, ktery ma primo funkci
apply_switch_optimizations() pro "Nintendo Switch (Nvidia Tegra X1 /
Maxwell 256 CUDA cores)". Odpovidajici kusy kodu:

  * scripts/build.py :: patch_libemucore_settings_defaults()
        - "v1.5-4248" vetev (soubor 12 162 984 B) — texture preload
  * scripts/build.py :: patch_preserve_user_data_on_reset()
        - "1. v1.5-4248 (Adreno & Switch)" — zachova memory cardy/achievementy
  * patches/patch_scale_multiplier.py :: patch_emucore_scale_clamp()
        - odstraneni 0.5f dolniho clampu rozliseni

Kazdy patch je DEZKOVE ZACHOVNY a pred aplikaci se overi presny puvodni
obsah. Nic se nehadam - pokud bajty nesedi, skript skonci.

POZOR - OPRAVA CHYBY
--------------------
Drivejsi verze tohoto skriptu prejmenovavala libvulkan.so -> libvulkad.so
(= vypnuti Vulkanu). To bylo SPATNE. Upstream pro Tegra X1 vyslovne
doporucuje VULKAN (Renderer = 14), protoze Nvidia driver je na Tegra
"desktop-grade" a Maxwell GM20B ma nativni hardwarove dual-source blending.
Vypnuti Vulkanu je tedy na Switchi krok zpet. Tato verze to nedela.

CO TENHLE SKRIPT NEDELA
-----------------------
Neprepisuje kod emulátoru. Tegra X1 profil je z velke casti nastaveni
PREFERENCES (XML v APK), ne v .so — viz docs/tegra-x1-patch-report.md.

POUZITI
-------
    python3 tools/patch_tegra_x1.py VSTUP.so [VYSTUP.so]
    python3 tools/patch_tegra_x1.py --check SOUBOR.so
    python3 tools/patch_tegra_x1.py --list
    python3 tools/patch_tegra_x1.py VSTUP.so VYSTUP.so --with-vulkan-bypass
"""

import sys
import os
import re
import hashlib
import struct
import subprocess
import argparse

EXPECTED_SIZE_4248 = 12_162_984   # build.py: vetev "adreno/4248"

# -------------------------------------------- spin-loop (Semaphore::Wait)
# PCSX2 ceka na semafor aktivnim spinem. Struktura (overeno na vsech 81 mist):
#
#     ldr  w8,[xN,#0xc08]     ; g_spin_cycles
#     cbz  w8, -> nanosleep   ; pomalou cestu (1 s!) vezme jen kdyz je 0
#     mov  w9, wzr
#   blok:  8x isb             ; <-- ZDRZENI
#     add  w9, w9, w8
#     cmp  w9, #0x1f4         ; 500
#     b.lo blok
#     add  w22, w22, w9
#     ldar w21,[xN]           ; <-- ZNOVU NACTENO S ACQUIRE
#     tbz  w21, #0x1f, ...    ; podminka ukonceni
#
# DULEZITE: razeni pameti dela 'ldar' (acquire), NE 'isb'. ISB neni datova
# bariera - ARM ARM vyslovne rika, ze ISB neradi datove pristupy. ISB je
# tady ciste zpozdeni, takze jeho vymena za 'yield' je PAMETOVE BEZPECNA.
#
# 'yield' (0xD503203F) je presne to, co pouziva linuxovy arm64 cpu_relax().
# POZOR na zmenu: 0xD503205F neni yield, ale WFE!
ISB_WORD      = 0xD5033FDF
YIELD_WORD    = 0xD503203F
ADD_W9_W9_W8  = 0x0B080129      # add w9, w9, w8
CMP_W9_500    = 0x7107D13F      # cmp w9, #0x1f4

# -------------------------------------------------------------- katalog

# (id, popis, ocekavany_offset, puvodni_bajty, nove_bajty)
# Offsety jsou jen pro reporting; hleda se podle OBSAHU, takze patch
# funguje i kdyby se binarka mierne posunula.
PATCHES = [
    dict(
        id="scale-unclamp",
        desc="Odstrani dolni clamp rozliseni (0.5f -> bez omezeni)",
        off=0x4BAB80,
        mode="pattern",
        old=bytes.fromhex("0158211e02102c1e0020221e404c211e"),
        new=bytes.fromhex("0158211e02102c1e0020221e2040201e"),
        # fmin s1,s0,s1 / fmov s2,#0.5 / fcmp s0,s2 / fcsel s0,s2,s1,mi
        #   -> posledni instrukce menena na: fmov s0, s1
        note="Umožní renderovat na 0.25x / 0.1x / 0.05x. "
             "Na slabém Tegra X1 největší jednotlivá páka na FPS.",
    ),
    dict(
        id="texture-preload-defaults",
        desc="Full Texture Hash Cache jako default (setDefaultSettings)",
        off=0x84179C,
        old=bytes.fromhex("00119f1a"),
        new=bytes.fromhex("40008052"),   # mov w0, #2
        mode="offset",   # 4B vzor ma 37 vyskytu -> musi se rizdit offsetem
        note="Méně zasekávání způsobených nahráváním textur za běhu.",
    ),
    dict(
        id="texture-preload-gssettings",
        desc="Full Texture Hash Cache fallback (GSSettings::Load)",
        off=0x4BAC34,
        old=bytes.fromhex("a3224039"),
        new=bytes.fromhex("43008052"),   # mov w3, #2
        mode="offset",   # 4B vzor neni unikatni -> rizdit se offsetem
        note="Zajistí stejnou hodnotu i při načtení uložených nastavení.",
    ),
    dict(
        id="preserve-user-data-1",
        desc="Reset presetu nemaže paměťové karty / achievementy / ovládání (call 1)",
        off=0x840F48,
        mode="pattern",
        old=bytes.fromhex("e1031f2a2200805223008052e4031f2ae5031f2a39a6fe97"),
        new=bytes.fromhex("e1031f2ae2031f2ae3031f2ae4031f2ae5031f2a1f2003d5"),
        note="Bezpečnostní síť: 'Safe/Optimal defaults' ti nesmaže savestavy.",
    ),
    dict(
        id="preserve-user-data-2",
        desc="Reset presetu nemaže paměťové karty / achievementy / ovládání (call 2)",
        off=0x840FD4,
        mode="pattern",
        old=bytes.fromhex("e1031f2a22008052e3031f2ae4031f2ae5031f2a16a6fe97"),
        new=bytes.fromhex("e1031f2ae2031f2ae3031f2ae4031f2ae5031f2a1f2003d5"),
        note="Totéž pro ApplyPerformancePreset.",
    ),
]

# Volitelny, NEOVERENY proti upstream zdroji (build.py ho jen kontroluje,
# neaplikuje). Aplikuj jen pokud vis, co delas.
OPTIONAL = [
    dict(
        id="vulkan-shim-hook",
        desc="[VYŽADUJE DODANÉ libvulkad.so] Přesměruje loader na libvulkad.so",
        off=None,            # hledá se podle obsahu, 2 vyskyty
        mode="multi",
        old_list=[(0x10728E, b"libvulkan.so"),  (0x1264CB, b"libvulkan.so.1"),
                  (0x1264F3, b"libvulkan.so")],
        note="Mechanismus z github.com/nckstwrt/NetherSX2-Turnip: "
             "libemucore.so se upraví, aby místo systémového libvulkan.so "
             "načítal DODANÝ libvulkad.so. Ten pak obalí skutečný "
             "libvulkan.so a vymění ICD ovladač (u Turnipu za Turnip). "
             "NENÍ to vypnutí Vulkanu - je to vstupní bod pro VÝMĚNU OVLADAČE. "
             "Bez vlastního libvulkan.so (=libvulkad.so) v APK tím Vulkan naopak ROZBÍJÍŠ.",
    ),
    dict(
        id="vulkan-format-bypass",
        desc="[NEPOTVRZENO] Obchází kontrolu podporovaných Vulkan formátů",
        off=0x65AFA0,
        mode="offset",
        old=bytes.fromhex("e1190054"),   # b.ne #0x65b2dc
        new=bytes.fromhex("1f2003d5"),   # nop
        note="build.py tento patch pouze VERIFIKUJE (čeká NOP na 0x65afa0 "
             "nebo 0x681e7c), sám ho neaplikuje — pochází z xdelta. "
             "Nemám jeho původní bajty, proto je vypnutý defaultně.",
    ),
    dict(
        id="spin-relax",
        desc="[EXPERIMENTÁLNÍ — ZMĚŘ] isb -> yield ve spin smyčkách semaforu",
        off=None,
        mode="spinrelax",     # hledá se podle signatury, 81 míst
        old=b"", new=b"",     # delkove zachovne, nahrazuje se 8x4B na miste
        note="PCSX2 aktivně čeká na semafor 8x 'isb' ve smyčce. ISB je na "
             "Cortex-A57 drahá instrukce (splachuje pipeline) a přitom NENÍ "
             "datová bariéra — řazení paměti zajišťuje 'ldar' před blokem, "
             "takže výměna za 'yield' (0xD503203F, = linuxový arm64 "
             "cpu_relax()) je PAMĚŤOVĚ BEZPEČNÁ.\n"
             "            SMĚR VÝKONU JE OVŠEM NEJEDNOZNAČNÝ a nebyl změřen: "
             "rychlejší spin = častější dotaz na semafor (nižší latence), "
             "ale také plné vytížení jádra při čekání. Na 4jádrovém Tegra X1 "
             "s připnutými vlákny (EE/GS/MTVU/driver na vlastní jádro) může "
             "pomoci; pokud jádra sdílí, může naopak škodit.\n"
             "            PROTO JE VYPNUTÝ. Zapni --with-spin-relax, odměř "
             "FPS a 1% low, a teprve podle výsledku se rozhodni.",
    ),
]


# -------------------------------------------------------------- pomoc

def die(msg, code=1):
    print(f"CHYBA: {msg}", file=sys.stderr)
    sys.exit(code)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def build_id(path):
    r = subprocess.run(["readelf", "-n", path], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        if "Build ID:" in l:
            return l.split()[-1].strip()
    return None


def elf_sections(path):
    r = subprocess.run(["readelf", "-S", "-W", path], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"readelf selhal na {path}")
    out = []
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) >= 7 and f[0].startswith("[") and f[1].startswith("."):
            try:
                out.append((f[1], int(f[3], 16), int(f[4], 16), int(f[5], 16)))
            except ValueError:
                continue
    return out


def find_all(data, needle):
    out, i = [], data.find(needle)
    while i != -1:
        out.append(i)
        i = data.find(needle, i + 1)
    return out


def isb_run8():
    return struct.pack("<8I", *([ISB_WORD] * 8))


def yield_run8():
    return struct.pack("<8I", *([YIELD_WORD] * 8))


def find_spin_blocks(data, run8=None):
    """Najde spin bloky Semaphore::Wait CISTE PODLE SIGNATURY (ne offsetu).

    Vyžaduje celý tvar:
        8x <run8> | add w9,w9,w8 | cmp w9,#0x1f4 | b.lo <zacatek bloku>
    Tim se zaroven vylouci 5 kalibracnich smycek jinde v binarce (ty maji
    za isb 'subs w8,w8,#1 ; b.ne' a nesmi se menit).

    run8=None hleda puvodni 8x isb; predat yield_run8() hleda jiz patchnuty
    stav (kvuli idempotenci).
    """
    run8, out = (isb_run8() if run8 is None else run8), []
    addw = struct.pack("<I", ADD_W9_W9_W8)
    cmpw = struct.pack("<I", CMP_W9_500)
    i = data.find(run8)
    while i != -1:
        j = i + 32
        if data[j:j + 4] == addw and data[j + 4:j + 8] == cmpw:
            w = struct.unpack_from("<I", data, j + 8)[0]
            if (w & 0xFF000010) == 0x54000000 and (w & 0xF) == 0x3:  # b.lo
                off = (w >> 5) & 0x7FFFF
                if off >= 0x40000:            # imm19 je signed
                    off -= 0x80000
                if j + 8 + off * 4 == i:      # skace zpet na zacatek bloku
                    out.append(i)
        i = data.find(run8, i + 1)
    return out


# -------------------------------------------------------------- akce

def do_patch(src, dst, extra=False, force=False, shim=False, spin=False):
    with open(src, "rb") as fh:
        data = bytearray(fh.read())

    print(f"Vstup   : {src}")
    print(f"          {len(data):,} B   sha256 {sha(src)}")
    print(f"          build-id {build_id(src)}")
    if len(data) != EXPECTED_SIZE_4248 and not force:
        die(f"velikost {len(data):,} neodpovida buildu 4248 "
            f"({EXPECTED_SIZE_4248:,}); pouzij --force pokud vis, co delas")
    print(f"          velikost odpovida 'v1.5-4248' vetvi z build.py\n")

    todo = list(PATCHES)
    if extra:
        todo += [p for p in OPTIONAL if p["id"] not in
                 ("vulkan-shim-hook", "spin-relax")]
    if shim:
        todo += [p for p in OPTIONAL if p["id"] == "vulkan-shim-hook"]
    if spin:
        todo += [p for p in OPTIONAL if p["id"] == "spin-relax"]
    applied = []
    for p in todo:
        if p.get("mode") != "multi" and len(p["old"]) != len(p["new"]):
            die(f"{p['id']}: patch neni delkove zachovny")
        if p.get("mode") == "spinrelax":
            blocks = find_spin_blocks(data)
            if not blocks:
                done = find_spin_blocks(data, yield_run8())
                if done:
                    print(f"  [=    ] {p['id']:<28} jiz aplikovano "
                          f"({len(done)} mist ma yield)")
                else:
                    print(f"  [!    ] {p['id']:<28} preskoceno "
                          f"(signatura spin smycky nenalezena)")
                continue
            run8, yld8 = isb_run8(), yield_run8()
            n_new = 0
            for b in blocks:
                if data[b:b + 32] == run8:
                    data[b:b + 32] = yld8
                    n_new += 1
            if n_new:
                applied.append(p)
                print(f"  [patch ] {p['id']:<28} {n_new}/{len(blocks)} mist "
                      f"-> yield")
                print(f"            {p['desc']}")
            else:
                print(f"  [=    ] {p['id']:<28} jiz aplikovano "
                      f"({len(blocks)} mist ma yield)")
            continue
        if p.get("mode") == "multi":
            n_ok = 0
            for off, old_s in p["old_list"]:
                new_s = old_s.replace(b"libvulkan", b"libvulkad")
                if data[off:off + len(old_s)] == old_s:
                    data[off:off + len(new_s)] = new_s
                    n_ok += 1
            if n_ok:
                applied.append(p)
                print(f"  [patch ] {p['id']:<28} {n_ok} mist -> libvulkad.so")
                print(f"            {p['desc']}")
            continue
        if p.get("mode") == "offset":
            # 4B vzory nejsou v binarce unikatni -> ridime se pevnym offsetem
            # (presne jako build.py: data[off:off+4] == orig)
            if data[p["off"]:p["off"] + len(p["old"])] == p["old"]:
                o = p["off"]
            elif data[p["off"]:p["off"] + len(p["new"])] == p["new"]:
                print(f"  [=    ] {p['id']:<28} jiz aplikovano")
                continue
            else:
                cur = data[p["off"]:p["off"] + len(p["old"])].hex()
                print(f"  [!    ] {p['id']:<28} preskoceno "
                      f"(na 0x{p['off']:x} je {cur}, cekal {p['old'].hex()})")
                continue
        else:
            hits = find_all(data, p["old"])
            if len(hits) != 1:
                if data.count(p["new"]) == 1:
                    print(f"  [=    ] {p['id']:<28} jiz aplikovano")
                    continue
                print(f"  [!    ] {p['id']:<28} preskoceno "
                      f"(nalezeno {len(hits)}x, cekal jsem presne 1)")
                continue
            o = hits[0]
        off_note = "" if o == p["off"] else f"  (build.py uvadi 0x{p['off']:x})"
        data[o:o + len(p["new"])] = p["new"]
        applied.append(p)
        print(f"  [patch ] {p['id']:<28} @0x{o:x}{off_note}")
        print(f"            {p['desc']}")

    if not applied:
        print("\nZadna zmena - binarka uz je patrne patchnuta.")

    before = elf_sections(src)
    with open(dst, "wb") as fh:
        fh.write(data)
    after = elf_sections(dst)

    print(f"\nZapsano: {dst}")
    print("\n=== VERIFIKACE ===")
    ok = True
    if len(data) != os.path.getsize(src):
        print("  ✗ zmenila se velikost"); ok = False
    else:
        print(f"  ✓ velikost zachovana: {len(data):,} B")
    if before != after:
        print("  ✗ zmenila se tabulka sekci"); ok = False
    else:
        print(f"  ✓ tabulka sekci identicka ({len(after)} sekci)")
    with open(dst, "rb") as fh:
        chk = fh.read()
    if chk.startswith(b"\x7fELF") and chk[0x12:0x14] == b"\xb7\x00":
        print("  ✓ platny ELF64 / AArch64")
    else:
        print("  ✗ neplatny ELF!"); ok = False
    for p in applied:
        if p.get("mode") == "multi":
            print(f"  ✓ {p['id']}: libvulkad.so {chk.count(b'libvulkad.so')}x "
                  f"(vyzaduje dodany libvulkad.so v APK)")
            continue
        if chk.count(p["new"]) < 1:
            print(f"  ✗ {p['id']} se neaplikoval"); ok = False
    if applied:
        print(f"  ✓ overeno {len(applied)} aplikovanych patchu")
    print(f"\n  ! build-id {build_id(dst)} (zastaraly - vyzadoval by relink)")
    print(f"  sha256 {sha(dst)}")
    if not ok:
        die("verifikace selhala", 2)
    print("\nHOTOVO.")


def do_check(path):
    with open(path, "rb") as fh:
        d = fh.read()
    print(f"{path}")
    print(f"  {len(d):,} B   sha256 {sha(path)}   build-id {build_id(path)}")
    if len(d) == EXPECTED_SIZE_4248:
        print(f"  ✓ velikost odpovida vetvi 'v1.5-4248' z build.py\n")
    else:
        print(f"  ! velikost NEodpovida 4248 ({EXPECTED_SIZE_4248:,})\n")
    for p in list(PATCHES) + list(OPTIONAL):
        if p.get("mode") == "multi":
            n_new = d.count(b"libvulkad")
            st = "APLIKOVANO" if n_new == 3 else ("neaplikovano" if d.count(b"libvulkan") == 3 else "??")
            print(f"  [{st:<12}] {p['id']:<28} {p['desc']}")
            continue
        if p.get("mode") == "spinrelax":
            n_isb = len(find_spin_blocks(d))
            n_yld = len(find_spin_blocks(d, yield_run8()))
            if n_yld and not n_isb:
                st = "APLIKOVANO"
            elif n_isb and not n_yld:
                st = "neaplikovano"
            elif n_isb and n_yld:
                st = "??CASTECNE"
            else:
                st = "??"
            print(f"  [{st:<12}] {p['id']:<28} {p['desc']}"
                  f"  ({n_yld} mist yield / {n_isb} mist isb)")
            continue
        # Overujeme VZDY na offsetu. Pocitani bajtu nespolehlive:
        #  - `nop` (1f2003d5) je v binarce 17 352x
        #  - sekvence `mov x1..x5, xzr; nop` (nova hodnota preserve-*) take
        #    vznika i jinde, protoze jde o bezny kompilatorni vzor
        is_new = d[p["off"]:p["off"] + len(p["new"])] == p["new"]
        is_old = d[p["off"]:p["off"] + len(p["old"])] == p["old"]
        st = "APLIKOVANO" if is_new else ("neaplikovano" if is_old else "??")
        print(f"  [{st:<12}] {p['id']:<28} {p['desc']}")
    nv = d.count(b"libvulkan.so")
    print()
    shim = d.count(b"libvulkad.so")
    if nv == 3 and shim == 0:
        msg = "OK - Vulkan zapnut (Switch ma pouzivat Vulkan)"
    elif shim == 3 and nv == 0:
        msg = "libvulkad.so hook AKTIVNI -> MUSIS dodat vlastni libvulkad.so, jinak Vulkan nejede"
    else:
        msg = "POZOR - necekana kombinace"
    print(f"  Vulkan: libvulkan.so {nv}x / libvulkad.so {shim}x -> {msg}")


def do_list():
    print("Katalog patchu (zdroj: github.com/mininxd/NetherSX2-patch)\n")
    for p in PATCHES + OPTIONAL:
        opt = "  [VOLITELNY]" if p in OPTIONAL else ""
        print(f"── {p['id']}{opt}")
        print(f"   {p['desc']}")
        if p.get("mode") == "multi":
            print("   offset " + ", ".join("0x%x" % o for o, _ in p["old_list"]))
        elif p.get("mode") == "spinrelax":
            print("   hledá se podle signatury (8x isb | add w9,w9,w8 | "
                  "cmp w9,#0x1f4 | b.lo)")
            print("   81 míst -> 81x 32 B nahrazeno (8x isb -> 8x yield)")
        elif p["off"] is None:
            print("   offset (zjišťuje se za běhu)")
        else:
            print(f"   offset 0x{p['off']:x}   {len(p['old'])} B -> {len(p['new'])} B")
        print(f"   {p['note']}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", help="vstupni libemucore.so")
    ap.add_argument("dst", nargs="?", help="vystupni soubor")
    ap.add_argument("--check", metavar="SOUBOR", help="pouze over stav")
    ap.add_argument("--list", action="store_true", help="vypis katalog patchu")
    ap.add_argument("--with-vulkan-bypass", action="store_true",
                    help="pridat i nepotvrzeny Vulkan format bypass")
    ap.add_argument("--with-spin-relax", action="store_true",
                    help="EXPERIMENTALNI: 8x isb -> 8x yield ve spin smyckach "
                         "semaforu (81 mist). Pametove bezpecne, ale SMER "
                         "VYKONU NEZMEREN -- odmer FPS!")
    ap.add_argument("--with-vulkan-shim-hook", action="store_true",
                    help="presmerovat loader na libvulkad.so (POUZE pokud dodavas "
                         "vlastni libvulkad.so - jinak rozbijes Vulkan)")
    ap.add_argument("--force", action="store_true",
                    help="ignorovat kontrolu velikosti")
    a = ap.parse_args()

    if a.list:
        do_list(); return
    if a.check:
        do_check(a.check); return
    if not a.src or not a.dst:
        ap.error("chybi VSTUP a/nebo VYSTUP (nebo pouzij --check / --list)")
    do_patch(a.src, a.dst, a.with_vulkan_bypass, a.force,
             a.with_vulkan_shim_hook, a.with_spin_relax)


if __name__ == "__main__":
    main()
