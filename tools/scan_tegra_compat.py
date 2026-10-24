#!/usr/bin/env python3
"""
scan_tegra_compat.py — staticka kontrola ARM64 binarky proti NVIDIA Tegra X1.

Tegra X1 (T210) = 4x Cortex-A57 (ARMv8.0-A) + 4x Cortex-A53 (ARMv8.0-A).
Cortex-A57 implementuje POUZE ARMv8.0-A.

Klicovy detail, ktery dela rozdil mezi "spadne" a "bezi":
  * PACIASP / AUTIASP / BTI   ... jsou kódovány v HINT prostoru. Na jadrech
    bez podpory (A57) se vykonaji jako NOP. => NEZAVADA.
  * RETAA / BRAA / XPACI-reg  ... skutecne ARMv8.3 instrukce. => SIGILL na A57.
  * LSE atomiky (ARMv8.1)     ... skutecne instrukce. Pokud je ale kompilator
    pouzil v outline-atomic helperu s `cbz <hwcap_flag>` guardem (LLVM
    -moutline-atomics), na A57 se preskoci do ldxr/stxr fallbacku. => bezpecne.
    Skript existenci guardu AUTOMATICKY OVERUJE.
  * CRC32 / Crypto            ... volitelne uz v ARMv8.0. Cortex-A57 CRC32 ma
    (viz gcc aarch64-cores.def: AARCH64_FL_CRC; llvm AArch64.td: AEK_CRC).
    Crypto Extension je volitelna a A57 ji v zakladu NEMA -> hlasit nalezy.

Pouziti:
    python3 tools/scan_tegra_compat.py <soubory .so>...
Vyzaduje: pip install --break-system-packages capstone
"""

import sys
import re
import subprocess
import collections

try:
    import capstone
except ImportError:
    sys.exit("Chybi capstone:  pip install --break-system-packages capstone")

# ------------------------------------------------------------- ISA sady

# ARMv8.1 Large System Extensions - skutecne instrukce
LSE = {
    "ldadd", "ldaddl", "ldaddb", "ldaddlb", "ldaddh", "ldaddlh",
    "ldclr", "ldclrl", "ldclrb", "ldclrlb", "ldclrh", "ldclrlh",
    "ldeor", "ldeorl", "ldeorb", "ldeorlb", "ldeorh", "ldeorlh",
    "ldset", "ldsetl", "ldsetb", "ldsetlb", "ldseth", "ldsetlh",
    "ldsmax", "ldsmaxl", "ldsmin", "ldsminl",
    "ldumax", "ldumaxl", "ldumin", "lduminl",
    "stadd", "staddl", "stclr", "stclrl", "steor", "steorl",
    "stset", "stsetl", "stsmax", "stsmaxl", "stsmin", "stsminl",
    "stumax", "stumaxl", "stumin", "stuminl",
    "swp", "swpl", "swpb", "swph", "swpal", "swpalb",
    "cas", "casa", "casl", "casal", "casb", "cash", "casp",
    "caspa", "caspl", "caspal",
}

# ARMv8.3 Pointer Authentication
PAC_HINT = {  # HINT prostor -> na A57 se vykona jako NOP, NEZAVADA
    # SP/ZR varianty
    "paciasp", "pacibsp", "paciaz", "pacibz", "paciza", "pacizb",
    "autiasp", "autibsp", "autiaz", "autibz", "autiza", "autizb",
    # 1716 varianty (implicitne X17/X16) - take HINT, na A57 NOP
    "pacia1716", "pacib1716", "autia1716", "autib1716",
    "xpaci", "xpacd", "bti",
}
PAC_REAL = {  # skutecne instrukce, NE v HINT prostoru -> na A57 SIGILL
    # POZOR: *1716 varianty sem NEPATRI. Jsou to aliasy na HINT
    # (binutils: pacia1716=HINT #0x8, pacib1716=HINT #0xa,
    #  autia1716=HINT #0xc, autib1716=HINT #0xe) -> na A57 se vykonaji jako NOP.
    "pacia", "pacib", "paciza", "pacizb", "pacda", "pacdb", "pacga",
    "autia", "autib", "autiza", "autizb", "autda", "autdb",
    "retaa", "retab", "braa", "brab", "braaz", "brabz",
    "blraa", "blrab", "blraaz", "blrabz", "ldraa", "ldrab",
}

BTI = {"bti"}                                  # ARMv8.5, HINT -> NOP
LDAPR = {"ldapr", "ldaprb", "ldaprh", "stlur", "stlurb", "stlurh"}   # ARMv8.3/8.4
MTE = {"irg", "addg", "subg", "stg", "stzg", "ldg", "st2g", "stz2g", "stgp"}

CRYPTO = {  # ARMv8.0 volitelne; A57 v zakladu NEMA
    "aese", "aesd", "aesmc", "aesimc",
    "sha1c", "sha1p", "sha1m", "sha1h", "sha1su0", "sha1su1",
    "sha256h", "sha256h2", "sha256su0", "sha256su1",
    "sha512h", "sha512h2", "sha512su0", "sha512su1",
    "sm3partw1", "sm3partw2", "sm3ss1", "sm3tt1a", "sm3tt1b", "sm3tt2a", "sm3tt2b",
    "sm4e", "sm4ekey", "rax1", "xar", "pmull", "pmull2",
}

FP_OPS = {  # FP16 (ARMv8.2) detekujeme pres .h arrangement nebo h-registry
    "fmla", "fmls", "fmul", "fadd", "fsub", "fdiv", "fsqrt", "fmax", "fmin",
    "fmaxnm", "fminnm", "fabs", "fneg", "frecpe", "frsqrte", "fmadd", "fmsub",
    "fnmadd", "fnmsub", "fcvt", "fcvtl", "fcvtn", "fcvtxn", "fcmp", "fcmpe",
    "fabd", "fmulx", "fnmul", "frsqrts", "frecps", "frecpx", "fmlal", "fmlsl",
}

# instrukce s vysokou latenci na A57 (nejsou plne pipeline-ovane)
SLOW = {"sdiv", "udiv", "fdiv", "fsqrt", "frecpe", "frsqrte"}


def classify(mnemonic: str, ops: str):
    """Vrati (kategorie, zavada: bool). zavada=True => na A57 SIGILL."""
    m = mnemonic.split(".")[0].lower()
    if m in LSE:
        return "LSE (ARMv8.1)", True          # zavada; overime guardem nize
    if m in PAC_REAL:
        return "PAC real (ARMv8.3)", True
    if m in LDAPR or m in MTE:
        return f"{m} (ARMv8.3+)", True
    if m in PAC_HINT or m in BTI:
        return "PAC/BTI v HINT prostoru", False   # NOP na A57
    if m in CRYPTO:
        return "CRYPTO (volitelne, A57 v zakladu nema)", True
    if m.startswith("crc32"):
        return "CRC32 (A57 podporuje)", False
    if m in FP_OPS:
        o = ops.lower()
        if re.search(r"\bh(\d|1\d|2\d|3[01])\b", o) or re.search(r"\.(\d+)?h\b", o):
            return "FP16 (ARMv8.2)", True
    return None, False


def find_text_section(path):
    r = subprocess.run(["readelf", "-S", "-W", path], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        f = line.split()
        # [Nr] Name Type Address Off Size ES Flg Lk Inf Al
        if len(f) >= 7 and f[1] == ".text":
            return dict(addr=int(f[3], 16), off=int(f[4], 16), size=int(f[5], 16))
    sys.exit(f"{path}: nenalezena sekce .text")


def scan(path):
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    md.detail = False

    sec = find_text_section(path)
    with open(path, "rb") as fh:
        fh.seek(sec["off"])
        code = fh.read(sec["size"])

    # prvni pruchod: nacti vse do pameti (potrebujeme kontext pro guardy)
    insns = []
    CHUNK = 1 << 18
    for base in range(0, len(code), CHUNK):
        insns.extend(md.disasm(code[base:base + CHUNK], sec["addr"] + base))

    cats = collections.Counter()
    examples = collections.defaultdict(list)
    total = ne_on = branches = loads = stores = nops = 0
    slow = collections.Counter()

    lse_guarded = lse_unguarded = 0
    lse_detail = []

    # index adresa -> pozice, pro rychle hledani
    by_addr = {i.address: n for n, i in enumerate(insns)}

    for n, ins in enumerate(insns):
        total += 1
        mn = ins.mnemonic.lower().split(".")[0]
        ops = ins.op_str.lower()

        c, fault = classify(ins.mnemonic, ops)
        if c:
            cats[c] += 1
            if len(examples[c]) < 3:
                examples[c].append(f"{ins.mnemonic} {ins.op_str} @0x{ins.address:x}")

            if c.startswith("LSE"):
                # hledej `cbz/cbnz` v 1..3 instrukcich pred nami, jehoz cil
                # preskakuje tuto LSE instrukci (= LLVM -moutline-atomics vzor)
                guarded = False
                for back in (1, 2, 3):
                    if n - back < 0:
                        break
                    prev = insns[n - back]
                    pm = prev.mnemonic.lower()
                    if pm in ("cbz", "cbnz"):
                        # cil skoku parsujeme z textu (vyhneme se md.detail,
                        # ktery by pruchod vyrazne zpomalil)
                        mt = re.search(r"#(0x[0-9a-f]+|\d+)", prev.op_str)
                        if mt:
                            tgt = int(mt.group(1), 0)
                            if tgt > ins.address:  # skoci az za LSE = preskoci ji
                                guarded = True
                                break
                if guarded:
                    lse_guarded += 1
                else:
                    lse_unguarded += 1
                    lse_detail.append(f"{ins.mnemonic} {ins.op_str} @0x{ins.address:x}")

        if mn in SLOW:
            slow[mn] += 1
        if re.search(r"\b[vbhsdq]\d+\b|\bv\d+\.\d", ops):
            ne_on += 1
        if mn.startswith(("b", "ret", "cb")):
            branches += 1
        if re.match(r"^(ldr|ldp|ldur|ld[rs]?[bhsw]|ldxr|ldar)", mn):
            loads += 1
        if re.match(r"^(str|stp|stur|st[lr]?[bhsw]|stxr|stlr)", mn):
            stores += 1
        if mn == "nop":
            nops += 1

    stats = dict(file=path, text_bytes=len(code), instructions=total,
                 neon=ne_on, branches=branches, loads=loads, stores=stores, nops=nops,
                 lse_guarded=lse_guarded, lse_unguarded=lse_unguarded,
                 lse_unguarded_list=lse_detail)
    findings = {c: dict(count=cats[c], examples=examples[c]) for c in cats}
    return stats, findings, slow


def main():
    for path in (sys.argv[1:] or ["4248/arm64-v8a/libemucore.so"]):
        stats, findings, slow = scan(path)
        print("=" * 74)
        print(f"SOUBOR: {path}")
        print("=" * 74)
        print(f"  .text                 : {stats['text_bytes']:,} bajtu")
        print(f"  instrukci             : {stats['instructions']:,}")
        print(f"  NEON/ASIMD operandu   : {stats['neon']:,} "
              f"({100*stats['neon']/max(1,stats['instructions']):.1f} %)")
        print(f"  load / store / skoku  : {stats['loads']:,} / {stats['stores']:,} / {stats['branches']:,}")
        print(f"  nop                   : {stats['nops']:,}")

        print("\n  --- KLASIFIKACE PODLE ARMv8.x ---")
        hard = []
        for c, d in sorted(findings.items(), key=lambda kv: -kv[1]["count"]):
            fault = ("ARMv8.1" in c or "ARMv8.2" in c or "ARMv8.3+" in c
                     or "CRYPTO" in c or "ARMv8.3" in c)
            tag = "SIGILL" if fault else "bezpecne"
            print(f"    [{tag:8s}] {c:<42s} {d['count']:>8,}x")
            for e in d["examples"]:
                print(f"               {e}")
            if fault:
                hard.append((c, d["count"]))

        print(f"\n  --- LSE ATOMIKY: guard overen ---")
        print(f"    s HWCAP guardem  (bezpecne) : {stats['lse_guarded']:,}")
        print(f"    BEZ guardu       (SIGILL!)  : {stats['lse_unguarded']:,}")
        for e in stats["lse_unguarded_list"][:10]:
            print(f"               {e}")

        print("\n  --- VYSOKA LATENCE NA A57 ---")
        for k, v in sorted(slow.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {k:<10s} {v:>8,}x")

        print("\n  --- VERDIKT ---")
        # LSE se pocita za bezpecne, pokud je KAZDA jeho instance kryta guardem
        real = [(c, n) for c, n in hard if not c.startswith("LSE")]
        if stats["lse_unguarded"]:
            real.append(("LSE bez HWCAP guardu", stats["lse_unguarded"]))
        if not real:
            print("    OK: binarka je z hlediska instrukcni sady na Cortex-A57")
            print("        (Tegra X1 / Nintendo Switch) bezpecna - nespadne na SIGILL.")
        else:
            print("    POZOR: nalezeny skutecne nebezpecne instrukce:")
            for c, n in real:
                print(f"      - {c}: {n:,}x")
        print()


if __name__ == "__main__":
    main()
