#!/usr/bin/env python3
"""
find_tegra_candidates.py -- katalog kandidatu na dalsi Tegra X1 patche
v libemucore.so (NetherSX2 v2.2n-4248).

PROC TENHLE NSTROJ
------------------
Prvni pokus o hledani dalsich patchu byl hruby sken (hledani `ldrsb`+shifty
v celem .text) a dal 1123 zasahu -- k nicemu. Bez symbolu (binarka je
stripped) a bez profilu ze zarizeni se nedá poznat, ktery z nich je horky
a ktery je studena cesta, ktera se zavola jednou za beh.

Tenhle nastroj proto nedela "najdi patch", ale "udelat poradek":

  [1] spin smycky -- sched_yield() uvnitr zpetne vetve. Na 4jadrovem
      Cortex-A57 (zadne SMT) spinujici vlakno sezere cele jadro.
  [2] konfiguracni struktura -- kde zije EmuConfig.Speedhacks (x21 =
      0x2604F20, EECycleSkip na +5), aby se daly pridavat dalsi knoby.
  [3] kolize -- zadny kandidat nesmi lezet v rozsahu jiz applied patchu.

CO NEUMI: urcit, ktery spin je doopravdy horky. To vyzaduje profil ze
zarizeni (fork uz diagnostiku ma: "pocitat sched_yield per vlakno").
Vystup je podklad pro rozhodnuti, ne rozhodnuti samo.

POUZITI
-------
    python3 tools/find_tegra_candidates.py [SOUBOR] [--json VYSTUP]

Vyžaduje capstone (pip install capstone).
"""

import argparse
import json
import struct
import sys

try:
    import capstone
except ImportError:
    sys.exit("Chybi capstone: pip install --break-system-packages capstone")

# Rozsahy uz aplikovanych patchi z tools/patch_tegra_x1.py.
# Zadny novy kandidat se nesmi dotknout techto bajtu -- jinak by zmenil
# 'expect' hodnotu, kterou port kontroluje.
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
    import subprocess
    out = subprocess.run(["readelf", "-SW", path],
                         capture_output=True, text=True).stdout
    import re
    m = re.search(r"\[\s*\d+\]\s+\.text\s+PROGBITS\s+([0-9a-f]+)\s+"
                  r"([0-9a-f]+)\s+([0-9a-f]+)", out)
    if not m:
        return 0x260000, 0xB5779C          # zname hodnoty pro tento build
    off, size = int(m.group(2), 16), int(m.group(3), 16)
    return off, off + size


def find_plt_slot(path, name="sched_yield"):
    """Odhadne adresu PLT stubu pro importovanou funkci."""
    import subprocess
    import re
    syms = subprocess.run(["readelf", "-sW", path],
                          capture_output=True, text=True).stdout
    idx = None
    n = 0
    for line in syms.splitlines():
        m = re.match(r"\s*\d+:\s+0+\s+0\s+FUNC\s+GLOBAL\s+DEFAULT\s+UND\s+(\S+)",
                     line)
        if not m:
            continue
        if m.group(1).startswith(name):
            idx = n
            break
        n += 1
    if idx is None:
        return None
    sec = subprocess.run(["readelf", "-SW", path],
                         capture_output=True, text=True).stdout
    m = re.search(r"\[\s*\d+\]\s+\.plt\s+PROGBITS\s+([0-9a-f]+)\s+"
                  r"([0-9a-f]+)\s+([0-9a-f]+)", sec)
    plt_va = int(m.group(1), 16)
    return plt_va + 32 + idx * 16


def call_sites(d, t0, t1, target):
    for off in range(t0, t1 - 3, 4):
        w = struct.unpack_from("<I", d, off)[0]
        if (w & 0xFC000000) != 0x94000000:      # BL
            continue
        imm = w & 0x3FFFFFF
        if imm & (1 << 25):
            imm -= (1 << 26)
        if off + imm * 4 == target:
            yield off


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("so", nargs="?", default="4248/arm64-v8a/libemucore_tegrax1.so")
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args()

    d = open(a.so, "rb").read()
    t0, t1 = text_bounds(a.so)
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    md.detail = True

    print("=" * 88)
    print(f"KANDIDATI NA DALSI TEGRA X1 PATCHE: {a.so}")
    print(f".text: 0x{t0:x}..0x{t1:x}  ({t1 - t0:,} B)   stripped: bez .symtab")
    print("=" * 88)

    # ---- [1] spin smycky -------------------------------------------------
    plt = find_plt_slot(a.so)
    if plt is None:
        print("\nsched_yield neni importovan -- spin smycky nelze najit toutou cestou")
        spins = []
    else:
        calls = list(call_sites(d, t0, t1, plt))
        spins = []
        for c in calls:
            lo, hi = c - 40 * 4, c + 12 * 4
            ins = list(md.disasm(d[lo:hi + 4], lo))
            for i in ins:
                if i.mnemonic.startswith("b.") and i.operands:
                    tgt = i.operands[0].imm
                    if lo <= tgt <= c:
                        pre = [x for x in ins if c - 20 <= x.address < c]
                        spins.append({
                            "addr": c, "loop_head": tgt,
                            "body": "; ".join(f"{x.mnemonic} {x.op_str}"
                                              for x in pre[-3:]),
                        })
                        break

        print(f"\n[1] SPIN SMYCKY (sched_yield uvnitr zpetne vetve)")
        print(f"    {len(spins)} z {len(calls)} volani sched_yield je ve smycce\n")
        print(f"    {'SITE':<12}{'ZACATEK SMYCKY':<16}TELO PRED YIELD")
        print("    " + "-" * 84)
        for s in spins:
            print(f"    0x{s['addr']:<10x}0x{s['loop_head']:<14x}{s['body'][:56]}")

    # ---- [2] konfiguracni struktura --------------------------------------
    print(f"\n[2] KONFIGURACNI STRUKTURA (EmuConfig.Speedhacks)")
    print("    Z VU_Thread::ExecuteVU, oblasti 0x4b24b0..0x4b2530:")
    print("      x21 = ADRP 0x2604000 + 0xf20   -> 0x2604F20")
    print("      +0   = priznaky (bit 5 testovan tbnz na 0x4b252c)")
    print("      +5   = EECycleSkip (ldrb w10,[x21,#5] -> MUL na 0x4b2500)")
    print("    Dalsi offsety teze struktury v dosahu (0x4b2000..0x4b2c00):")
    for i in md.disasm(d[0x4b2000:0x4b2c00], 0x4b2000):
        if i.mnemonic in ("ldrb", "ldr", "ldrsw", "ldrh") and "x21" in i.op_str:
            print(f"      0x{i.address:x}: {i.mnemonic:<6}{i.op_str}")

    # ---- [3] kolize -------------------------------------------------------
    print(f"\n[3] KONTROLA KOLIZI")
    watched = dict(WATCHED)
    for off, (nm, ln) in APPLIED.items():
        for k in range(off, off + ln):
            watched.setdefault(k, f"nase: {nm}")
    bad = []
    for s in spins:
        for k in range(s["loop_head"], s["addr"] + 4):
            if k in watched:
                bad.append((s["addr"], k, watched[k]))
                break
    if bad:
        for sa, k, why in bad:
            print(f"    !! spin 0x{sa:x} zasahuje 0x{k:x} ({why})")
    else:
        print(f"    OK: zadny z {len(spins)} kandidatu nelezi v rozsahu")
        print(f"        applied patchu ani hlidanych mist ({len(watched)} bajtu)")

    print("\n" + "=" * 88)
    print("CO Z TOHO PLYNE")
    print("=" * 88)
    print(f"  - {len(spins)} spin smycek je katalogizovano a zadna nekoliduje.")
    print("  - Ktera z nich je horka, z Binarky POZNAT NELZE (stripped, bez profilu).")
    print("  - Fork uz diagnostiku ma (sched_yield per vlakno) -- skutecne")
    print("    poradi se musi vzit z logu ze zarizeni, ne odhadem.")
    print("  - VU cycle steal (0x4b2500) uz fork ma; EE CycleRate je v jadre")
    print("    pritomen jako retezec, ale jde o nastaveni, ne o patch.")

    if a.json_out:
        json.dump({"spins": spins, "applied": {hex(k): v[0]
                                               for k, v in APPLIED.items()}},
                  open(a.json_out, "w"), indent=2)
        print(f"\nJSON: {a.json_out}")


if __name__ == "__main__":
    main()
