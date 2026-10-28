#!/usr/bin/env python3
"""Vytvori ds2patcher_bez_kontroly_verze.exe z originalniho ds2patcher.exe
(pomocny nastroj z instalateru cestiny darksouls2cz 1.11).

Originalni patcher pred importem porovna MD5 souboru hry
(GameDataEbl.bhd) s ocekavanou hodnotou v md5-cryptedorig.txt
(38bb57bb292cc3e1773d0ee6873d0351). Kdyz nesedi, odmitne pokracovat
("Neznama verze hry Dark Souls 2!") a pracovni soubory premaze.

Tato uprava jediny podmineny skok za porovnanim (je fail, VA 0x40312a)
nahradi 6x NOP, takze patcher projde dal vetvi "Verze v poradku.".
Nic jineho se nemeni.

POUZIVEJ JEN s puvodnim Dark Souls II (Steam App 236430), NE SotFS,
a jen kdyz GameDataEbl.bhd ma 760042 B a GameDataEbl.bdt 5400821795 B
(layout archivu verze 1.10). Predem zalohuj GameDataEbl.bhd/.bdt!

Pouziti: python3 tools/patch_ds2patcher.py <ds2patcher.exe> [vystup.exe]
"""
import hashlib
import struct
import sys

EXPECTED_SHA256 = "836f0459a2c7f2bef718df396a60496c09ea0df0aba63805ffd2baec5eb8278a"  # pri sestaveni prepise nize uvedena konstanta
GATE_FILE_OFFSET = 0x312A
GATE_VA = 0x40312A
GATE_BYTES = bytes.fromhex("0f84a40b0000")  # je 0x403cd4 (fail cleanup)
PATCH_BYTES = b"\x90" * 6


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "ds2patcher_bez_kontroly_verze.exe"
    d = bytearray(open(src, "rb").read())
    sha = hashlib.sha256(d).hexdigest()
    print("vstup:", src, len(d), "B, sha256", sha)
    if sha != EXPECTED_SHA256:
        print("CHYBA: sha256 vstupu nesedi na extrahovany ds2patcher.exe "
              f"({EXPECTED_SHA256}) - nic nemenim.")
        return 1
    got = bytes(d[GATE_FILE_OFFSET:GATE_FILE_OFFSET + 6])
    if got != GATE_BYTES:
        print(f"CHYBA: na offsetu 0x{GATE_FILE_OFFSET:x} jsou bajty "
              f"{got.hex(' ')}, cekal jsem {GATE_BYTES.hex(' ')} - nic nemenim.")
        return 1
    d[GATE_FILE_OFFSET:GATE_FILE_OFFSET + 6] = PATCH_BYTES
    open(out, "wb").write(d)
    # verifikace: znovu nacist, zkontrolovat jen tech 6 bajtu
    v = open(out, "rb").read()
    orig = open(src, "rb").read()
    diff = [i for i in range(len(orig)) if orig[i] != v[i]]
    assert diff == list(range(GATE_FILE_OFFSET, GATE_FILE_OFFSET + 6)), diff
    print(f"OK: {out} (sha256 {hashlib.sha256(v).hexdigest()}); "
          f"zmeneno presne 6 bajtu @0x{GATE_FILE_OFFSET:x} "
          f"(VA {GATE_VA:#x}: je fail -> nop*6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
