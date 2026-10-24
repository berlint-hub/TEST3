#!/usr/bin/env python3
"""
verify_nx_compat.py — overi, ze patchnuty libemucore.so porad vyhovuje portu
NetherSX2_nx (<https://github.com/NaGaa95/NetherSX2_nx>).

KONTEXT
-------
NetherSX2_nx bere Android jadro `libemucore.so`, **patchuje ho za behu** a spousti
ho v minimalni android-like vrstve na Horizon OS. Dve veci jsou kriticke:

1. DETEKCE JADRA — port hleda retezec "v2.2n-4248" na vaddr 0xd4436:

       if (!memcmp(load_base + 0xd4436, "v2.2n-4248", 10))
           g_core_version = CORE_VER_V22N_4248;
       ...
       if (g_core_version == CORE_VER_UNKNOWN) return;   // neaplikuje se NIC

2. APLIKACE PATCHU — kazdy zaznam v `g_patches_4248` ma pole `expect`.
   Pokud se bajty na `vaddr` NEROVNAJI `expect`, port patch **tise preskoci**
   (zadny pady, ale funkce chybi).

Pokud by nas patch prepsal nejaky bajt, na ktery se port diva pres `expect`,
port by prestal aplikovat svuj patch — a to je presne ta chyba, kterou tento
skript hleda.

POUZITI
-------
    python3 tools/verify_nx_compat.py PATCHNUTE.so
    python3 tools/verify_nx_compat.py PATCHNUTE.so --nx-src /cesta/k/NetherSX2_nx

Vyzaduje: git clone --depth 1 https://github.com/NaGaa95/NetherSX2_nx.git
"""

import sys
import os
import re
import struct
import argparse

VERSION_OFFSET = 0xD4436
VERSION_STRING = b"v2.2n-4248"

# Zdrojove umisteni tabulky v portu
NX_PATCHES_REL = "source/hooks/patches.c"
NX_TABLE = "g_patches_4248"


def nx_patch_table(nx_src):
    """Vytahne g_patches_4248 z patches.c portu."""
    path = os.path.join(nx_src, NX_PATCHES_REL)
    if not os.path.exists(path):
        sys.exit(f"Nenalezeno {path}\nNaklonuj: git clone --depth 1 "
                 f"https://github.com/NaGaa95/NetherSX2_nx.git")
    src = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(re.escape(NX_TABLE) + r"\[\] = \{(.*?)\n\};", src, re.S)
    if not m:
        sys.exit(f"{NX_TABLE} nenalezena v {path}")
    rows = []
    for vaddr, expect, what in re.findall(
            r"\{\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),\s*[^,]+,\s*\"([^\"]*)\"\s*\}",
            m.group(1)):
        rows.append((int(vaddr, 16), int(expect, 16), what))
    return rows


def nx_extra_sites(nx_src):
    """Vytahne fork-specificka mista, ktera NEJSOU v g_patches_4248.

    Fork berlint-hub/NetherSX2_nx pridal patch_vu_steal_4248() -- samostatnou
    funkci s vlastni podminkou (ne polozku tabulky). Ma svuj EXPECT a pri
    neshode se jen zaloguje a vrati, takze stejne jako u tabulky plati:
    tiche preskoceni, zadny pad. Musi se proto hlidat zvlast.
    """
    path = os.path.join(nx_src, NX_PATCHES_REL)
    if not os.path.exists(path):
        return []
    src = open(path, encoding="utf-8", errors="replace").read()
    out = []
    m_addr = re.search(r"#define\s+VU_STEAL_4248_ADDR\s+(0x[0-9a-fA-F]+)u?", src)
    m_exp = re.search(r"#define\s+VU_STEAL_4248_EXPECT\s+(0x[0-9a-fA-F]+)u?", src)
    if m_addr and m_exp:
        out.append((int(m_addr.group(1), 16), int(m_exp.group(1), 16),
                    "VU cycle steal (fork; prefs EmuCore/Speedhacks/vuCycleSteal)"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("so", help="patchnuty libemucore.so")
    ap.add_argument("--nx-src", default=None,
                    help="cesta ke klonu NetherSX2_nx (vychozi: zkusime "
                         "fork berlint-hub, pak upstream, pak ./NetherSX2_nx)")
    ap.add_argument("--base", default=None,
                    help="puvodni (nepatchnuty) soubor pro porovnani")
    a = ap.parse_args()

    # Zdroj portu: fork (cilovy produkt) ma prednost pred cistym upstreamem.
    if a.nx_src:
        nx_src = a.nx_src
    else:
        import glob
        candidates = ["/home/user/_nsx2nx_fork", "/home/user/_nsx2nx"] + \
                     sorted(glob.glob("/home/user/NetherSX2_nx*")) + \
                     ["NetherSX2_nx"]
        nx_src = next((c for c in candidates
                       if os.path.exists(os.path.join(c, NX_PATCHES_REL))), None)
        if nx_src is None:
            sys.exit("Nenalezen zdrojovy strom NetherSX2_nx. Naklonuj:\n"
                     "  git clone --depth 1 -b arena/2e44eb02-nethersx2-nx "
                     "https://github.com/berlint-hub/NetherSX2_nx.git\n"
                     "a pridej --nx-src CESTA")

    data = open(a.so, "rb").read()
    base = open(a.base, "rb").read() if a.base else None

    print("=" * 84)
    print(f"SOUBOR: {a.so}  ({len(data):,} B)")
    print("=" * 84)

    ok = True

    # --- 1. detekce jadra -------------------------------------------------
    print("\n[1] DETEKCE JADRA PORTEM")
    got = data[VERSION_OFFSET:VERSION_OFFSET + len(VERSION_STRING)]
    if got == VERSION_STRING:
        print(f"    ✓ 0x{VERSION_OFFSET:x} obsahuje {VERSION_STRING.decode()!r}")
        print("      -> port jadro rozpozna jako CORE_VER_V22N_4248 a bude patchovat")
    else:
        print(f"    ✗ 0x{VERSION_OFFSET:x} = {got!r}, ocekavano {VERSION_STRING!r}")
        print("      -> port skonci na CORE_VER_UNKNOWN a NEAPLIKUJE ZADNE PATCHE")
        ok = False

    # --- 2. expect hodnoty ------------------------------------------------
    rows = nx_patch_table(nx_src)
    print(f"\n[2] KONTROLA {len(rows)} 'expect' HODNOT Z g_patches_4248")
    print(f"    (zdroj: {nx_src}/{NX_PATCHES_REL})\n")
    print(f"    {'VADDR':<10}{'EXPECT':<12}{'VYSTUP':<12}{'CO':<34}STAV")
    print("    " + "-" * 92)

    collisions = 0
    for vaddr, expect, what in rows:
        if vaddr + 4 > len(data):
            print(f"    0x{vaddr:<8x}{'':<12}{'':<12}{what:<34}MIMO ROZSAH")
            continue
        cur = struct.unpack("<I", data[vaddr:vaddr + 4])[0]
        if cur == expect:
            status = "OK - port aplikuje"
        else:
            if base is not None and vaddr + 4 <= len(base):
                b = struct.unpack("<I", base[vaddr:vaddr + 4])[0]
                if b == expect:
                    status = "!! KOLIZE - nas patch rozbil expect"
                    collisions += 1
                    ok = False
                else:
                    status = "nesedi uz v base (port preskoci)"
            else:
                status = "nesedi (dej --base pro detail)"
                if base is None:
                    ok = False
        print(f"    0x{vaddr:<8x}0x{expect:<10x}0x{cur:<10x}{what:<34}{status}")

    print(f"\n    Kolizi: {collisions}")

    # --- 3. fork-specificka mista mimo tabulku -----------------------------
    extra = nx_extra_sites(nx_src)
    print(f"\n[3] KONTROLA {len(extra)} FORK-SPECIFICKYCH MIST (mimo g_patches_4248)")
    if not extra:
        print("    (zdroj nema zadna -- cisty upstream?)")
    for vaddr, expect, what in extra:
        if vaddr + 4 > len(data):
            print(f"    0x{vaddr:<8x}{'':<12}{'':<12}{what:<34}MIMO ROZSAH")
            continue
        cur = struct.unpack("<I", data[vaddr:vaddr + 4])[0]
        if cur == expect:
            status = "OK - patch se aplikuje"
        else:
            status = "!! NESEDI - patch se NEAPLIKUJE"
            collisions += 1
            ok = False
        print(f"    0x{vaddr:<8x}0x{expect:<10x}0x{cur:<10x}{what:<34}{status}")

    # --- 4. souhrn --------------------------------------------------------
    print("\n" + "=" * 84)
    if ok:
        print("VERDIKT: vystup je KOMPATIBILNI s NetherSX2_nx.")
        print("         Port jadro rozpozna a aplikuje vsech "
              f"{len(rows)} svych patchu.")
    else:
        print("VERDIKT: NEKOMPATIBILNI - viz vyse.")
    print("=" * 84)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
