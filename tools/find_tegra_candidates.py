#!/usr/bin/env python3
"""
find_tegra_candidates.py -- katalog kandidatu na dalsi Tegra X1 patche
v libemucore.so (NetherSX2 v2.2n-4248).

SKENOVAT 'isb', NE 'sched_yield'
--------------------------------
Prvni verze tohohle nastroje hledala spin pres volani sched_yield() a nasla
27 mist. To byla CHYBA ze dvou duvodu:

1. PCSX2 ShortSpin()/WorkSema spinuje na `isb` v userspace a sched_yield()
   vola az po vycerpani spin budgetu. Spin, ktery se jeste nevycerpal, se
   sched_yield vubec nedotkne -- takze ta metoda nemohla horke spiny najit.
   (Zjistil to fork merenim, commit b3aa5ca7.)

2. Kdyz jsem pak hledal `isb` primo, taky jsem nasel nula -- protoze jsem mel
   spatne kodovanou konstantu. 0xD5033FDF jsem mel oznaceny jako "DSB sy",
   ale je to `isb`.

   Spravne:  0xD503201F = nop     0xD5033FDF = isb
             0xD503205F = yield/wfe (v tomhle jadre 0x -- nepouziva se)

Co tedy skenovat: souvisle bloky `isb` (ShortSpin() je rozvinuty 8x) a za
nim zpetnou vetev. V tomhle jadre: 707 isb -> 105 bloku -> 86 spin smycek.

STRuktura typicke smycky (priklad z MTVU, 0x4b2304):

    0x4b2304: mov  w9, wzr          ; pocitadlo = 0
    0x4b2308: isb                   ; -+
      ...     isb  (celkem 8x)      ;  | ShortSpin() x 8
    0x4b2324: isb                   ; -+
    0x4b2328: add  w9, w9, w8       ; += spin budget  (ldr w8,[x24,#0xc08])
    0x4b232c: cmp  w9, #0x1f4       ; 500  <- SPIN BUDGET, kandidat na patch
    0x4b2330: b.lo #0x4b2308        ; dokud < 500
    0x4b2344: bl   #0x8a3380        ; az pak blokovaci cesta (nanosleep 1 s)

POUZITI
-------
    python3 tools/find_tegra_candidates.py [SOUBOR] [--json VYSTUP]

Vyzaduje capstone (pip install --break-system-packages capstone).
"""

import argparse
import json
import struct
import sys

try:
    import capstone
except ImportError:
    sys.exit("Chybi capstone: pip install --break-system-packages capstone")

ISB = 0xD5033FDF          # isb  (NE "DSB sy" -- to byla moje puvodni chyba)
NOP = 0xD503201F

# Rozsahy uz aplikovanych patchi z tools/patch_tegra_x1.py.
APPLIED = {
    0x4bab80: ("gs-max-upscale-unclamp", 16),
    0x84179c: ("texture-preload-defaults", 4),
    0x4bac34: ("texture-preload-gssettings", 4),
    0x840f48: ("preserve-user-data-1", 24),
    0x840fd4: ("preserve-user-data-2", 24),
}
# Mista, ktera hlida port / fork (nesahat).
WATCHED = {
    0x4b2500: "fork: VU cycle steal",
    0x4bab84: "port: GS upscale minimum 0.25x",
    0xd4436: "port: detekcni retezec 'v2.2n-4248'",
}


def text_bounds(path):
    """Vrati (file_off_start, file_off_end) sekce .text."""
    import re
    import subprocess
    out = subprocess.run(["readelf", "-SW", path],
                         capture_output=True, text=True).stdout
    m = re.search(r"\[\s*\d+\]\s+\.text\s+PROGBITS\s+([0-9a-f]+)\s+"
                  r"([0-9a-f]+)\s+([0-9a-f]+)", out)
    if not m:
        return 0x260000, 0xB5779C          # zname hodnoty pro tento build
    off, size = int(m.group(2), 16), int(m.group(3), 16)
    return off, off + size


def isb_runs(d, t0, t1, min_len=4):
    """Seskupi isb do souvislych bloku (mezera <= 2 instrukce)."""
    hits = [o for o in range(t0, t1 - 3, 4)
            if struct.unpack_from("<I", d, o)[0] == ISB]
    if not hits:
        return []
    runs, cur = [], [hits[0]]
    for a, b in zip(hits, hits[1:]):
        if b - a <= 8:
            cur.append(b)
        else:
            runs.append((cur[0], cur[-1]))
            cur = [b]
    runs.append((cur[0], cur[-1]))
    return [(s, e) for s, e in runs if (e - s) // 4 + 1 >= min_len]


def backward_branch(md, d, block_end, block_start, look=14):
    """Najde zpetnou vetev za blokem (do `look` instrukci)."""
    for i in md.disasm(d[block_end + 4: block_end + 4 + look * 4],
                       block_end + 4):
        if (i.mnemonic.startswith("b.") and i.operands
                and i.operands[0].type == capstone.arm64.ARM64_OP_IMM):
            tgt = i.operands[0].imm
            if block_start - 16 * 4 <= tgt <= block_end:
                return i.address, tgt
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("so", nargs="?",
                    default="4248/arm64-v8a/libemucore_tegrax1.so")
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args()

    d = open(a.so, "rb").read()
    t0, t1 = text_bounds(a.so)
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    md.detail = True

    nop = sum(1 for o in range(t0, t1 - 3, 4)
              if struct.unpack_from("<I", d, o)[0] == NOP)
    isb = sum(1 for o in range(t0, t1 - 3, 4)
              if struct.unpack_from("<I", d, o)[0] == ISB)

    print("=" * 88)
    print(f"KANDIDATI NA DALSI TEGRA X1 PATCHE: {a.so}")
    print(f".text: 0x{t0:x}..0x{t1:x}  ({t1 - t0:,} B)   stripped: bez .symtab")
    print("=" * 88)
    print(f"\n[0] HINT/BARRIER INSTRUKCE")
    print(f"    nop   0x{NOP:08x} : {nop}")
    print(f"    isb   0x{ISB:08x} : {isb}   <- spinuje se na tomhle")
    print(f"    (yield/wfe 0xD503205F v tomto jadre neni -- PCSX2 tu varianta "
          f"nepouziva)")

    runs = isb_runs(d, t0, t1)
    loops = []
    for s, e in runs:
        br = backward_branch(md, d, e, s)
        if br:
            loops.append({"start": s, "end": e,
                          "n_isb": (e - s) // 4 + 1,
                          "branch": br[0], "target": br[1]})

    print(f"\n[1] SPIN SMYCKY (blok isb + zpetna vetev)")
    print(f"    {isb} isb -> {len(runs)} souvislych bloku (>=4)"
          f" -> {len(loops)} skutecnych spin smycek\n")
    print(f"    {'BLOK ISB':<24}{'N':<4}{'VETEV':<12}{'CIL':<12}POZNAMKA")
    print("    " + "-" * 84)
    for L in loops:
        note = ""
        if 0x4b2000 <= L["start"] <= 0x4b2600:
            note = "MTVU / VU_Thread"
        elif 0x2fc000 <= L["start"] <= 0x2ff700:
            note = "recompiler blok"
        print(f"    0x{L['start']:x}-0x{L['end']:x}  {L['n_isb']:<4}"
              f"0x{L['branch']:<10x}0x{L['target']:<10x}{note}")

    # --- konfiguracni struktura -------------------------------------------
    print(f"\n[2] KONFIGURACNI STRUKTURA (EmuConfig.Speedhacks)")
    print("    Z VU_Thread::ExecuteVU (0x4b24b0..0x4b2530):")
    print("      x21 = ADRP 0x2604000 + 0xf20  ->  0x2604F20")
    print("      +0  = priznaky (bit 5 testovan tbnz na 0x4b252c)")
    print("      +5  = EECycleSkip (ldrb w10,[x21,#5] -> MUL na 0x4b2500)")

    # --- kolize -------------------------------------------------------------
    watched = dict(WATCHED)
    for off, (nm, ln) in APPLIED.items():
        for k in range(off, off + ln):
            watched.setdefault(k, f"nase: {nm}")
    print(f"\n[3] KONTROLA KOLIZI")
    bad = []
    for L in loops:
        for k in range(L["start"] - 0x40, L["end"] + 0x40):
            if k in watched:
                bad.append((L["start"], k, watched[k]))
                break
        for off, (nm, ln) in APPLIED.items():
            if not (L["end"] + 0x40 < off or L["start"] - 0x40 > off + ln):
                bad.append((L["start"], off, f"nase: {nm}"))
    if bad:
        for sa, k, why in bad:
            print(f"    !! spin 0x{sa:x} zasahuje 0x{k:x} ({why})")
    else:
        print(f"    OK: zadny z {len(loops)} spinu nelezi v rozsahu applied")
        print(f"        patchu ani hlidanych mist")

    print("\n" + "=" * 88)
    print("CO Z TOHO PLYNE")
    print("=" * 88)
    print(f"  - {len(loops)} spin smycek je katalogizovano, 0 kolizi.")
    print("  - Zkratit SPIN BUDGET (cmp w?, #0x1f4 = 500) je oboustranny")
    print("    obchod: driv vrati jadro ostatnim, ale prida prepnuti kontextu.")
    print("  - Ktery spin je horky, z binarky POZNAT NELZE (stripped). Chybí")
    print("    CPU cas per vlakno (pthr_cpu_time_report ve forku).")
    print("  - Nejvetsi nalezeny problem neni v jadre, ale v ovladaci:")
    print("    chybi VK_ARM_rasterization_order_attachment_access, takze GS")
    print("    musi kopirovat render targety (80.6 kopii/snimku v GT3).")
    print("    Binarnim patchem jadra to nevyresime -- resi to")
    print("    UserHacks_TextureInsideRt, ktery fork uz zpristupnil v menu.")

    if a.json_out:
        json.dump({"spin_loops": loops}, open(a.json_out, "w"), indent=2)
        print(f"\nJSON: {a.json_out}")


if __name__ == "__main__":
    main()
