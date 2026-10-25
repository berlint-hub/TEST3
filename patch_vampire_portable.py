#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binární patch Vampire: The Masquerade - Redemption (Vampire.exe):
hra si hned při startu sama nastaví pracovní adresář na složku,
kde leží její EXE (SetCurrentDirectoryA na adresář z GetModuleFileNameA).

Proč: hra ukládá nastavení i savy vůči pracovnímu adresáři procesu
  - masquerade.ini = GetCurrentDirectoryA + "masquerade.ini" (0x4ceca0),
  - savy = relativní "SaveGames\SP%d\..." (mainSave.cpp, 0x428df2),
  - i herní data čte relativně.
Když launcher (autorun/Wine frontend/zástupce) nastaví jiný pracovní
adresář, options i savy skončí jinde. Po patchi je to jedno - hra
si pracovní adresář srovná sama, žádný Python ani wrapper netřeba.

Jak patch funguje (minimální zásah, jen 3 změny):
  1) AddressOfEntryPoint se přesměruje na náš ~160 B stub ve volném
     místě na konci .text (slack za VirtualSize),
  2) .text VirtualSize se zarovná na SizeOfRawData, aby stub byl mapovaný,
  3) stub: GetModuleFileNameA -> smaže jméno exe z cesty ->
     GetProcAddress(GetModuleHandleA("KERNEL32.dll"),
     "SetCurrentDirectoryA") -> SetCurrentDirectoryA(složka exe) ->
     skok na původní entry point. Při jakékoli chybě stub tiše
     pokračuje původním startem. Stub je position-independent
     (delta přes call/pop), takže funguje i při relokaci image.

Výstup je vždy Vampire_portable.exe (originál zůstává nedotčený).
Patch je staticky ověřený (pefile + disassembler + emulace stubu),
ale v této dílně nejde spustit - před použitím si originál zazálohuj.

Použití: python3 patch_vampire_portable.py Vampire.exe [-o vystup.exe]
"""

import hashlib
import struct
import sys
from pathlib import Path

EXPECTED_SHA256 = "dd647078a6bf1ed9e1f36e6fe2d37bbd7fe2e1543aca220a3b5d9302dfa2b886"
IMAGE_BASE = 0x400000
ORIG_EP_VA = 0x4DF343            # původní entry point
IAT_GetModuleFileNameA = 0x4EB064
IAT_GetModuleHandleA = 0x4EB0A8
IAT_GetProcAddress = 0x4EB148
KERNEL32_NAME_VA = 0x4F1E0A      # řetězec "KERNEL32.dll" v import deskriptoru
CAVE_RVA = 0xEAEE0               # .text RVA 0x1000 + VirtualSize 0xe9ee0
CAVE_FILE_OFF = 0xEAEE0          # .text RawPtr 0x1000 + 0xe9ee0
CAVE_SIZE = 0x120                # 288 B slacku do konce raw .text
TEXT_NEW_VSIZE = 0xEA000


def build_stub(cave_va):
    """Sestaví stub; vrací (bytes, offset_jmp_eax). Dvoufázové skoky přes fixupy."""
    code = bytearray()
    fixups = []  # (offset_rel32_policka, label)
    labels = {}

    def emit(b):
        code.extend(b)

    def mark(name):
        labels[name] = len(code)

    def jz32(label):
        emit(b"\x0f\x84")
        fixups.append((len(code), label))
        emit(b"\x00\x00\x00\x00")

    emit(b"\x53")                                # push ebx
    emit(b"\x56")                                # push esi
    emit(b"\x57")                                # push edi
    emit(b"\x55")                                # push ebp
    emit(b"\xe8\x00\x00\x00\x00")                # call next
    pop_off = len(code)                          # sem ukazuje call
    emit(b"\x5b")                                # pop ebx  (ebx = runtime VA tehle instrukce)
    emit(b"\x81\xeb" + struct.pack("<I", cave_va + pop_off))  # sub ebx, linkVA -> delta
    emit(b"\x81\xec\x04\x01\x00\x00")            # sub esp, 0x104   (buffer = esp)
    # GetModuleFileNameA(NULL, buf, 0x104)
    emit(b"\x8d\x04\x24")                        # lea eax, [esp]
    emit(b"\x68\x04\x01\x00\x00")                # push 0x104
    emit(b"\x50")                                # push eax (buf)
    emit(b"\x6a\x00")                            # push 0 (hModule)
    emit(b"\x8d\x83" + struct.pack("<I", IAT_GetModuleFileNameA))  # lea eax,[ebx+IAT]
    emit(b"\x8b\x00")                            # mov eax, [eax]
    emit(b"\xff\xd0")                            # call eax
    # najdi poslední '\' v buf (inline strrchr; eax = poslední výskyt, edi skenuje)
    emit(b"\x8d\x3c\x24")                        # lea edi, [esp]
    emit(b"\x33\xc0")                            # xor eax, eax
    mark("scan")
    emit(b"\x8a\x17")                            # mov dl, [edi]
    emit(b"\x84\xd2")                            # test dl, dl
    jz_done_pos = len(code)
    emit(b"\x74\x00")                            # jz done (rel8, dopocitam)
    emit(b"\x80\xfa\x5c")                        # cmp dl, '\'
    emit(b"\x75\x02")                            # jne +2 (preskoc mov eax,edi)
    emit(b"\x8b\xc7")                            # mov eax, edi
    emit(b"\x47")                                # inc edi
    jmp_pos = len(code)
    emit(b"\xeb\x00")                            # jmp scan (rel8, dopocitam)
    mark("done")
    code[jz_done_pos + 1] = (labels["done"] - (jz_done_pos + 2)) & 0xFF
    code[jmp_pos + 1] = (labels["scan"] - (jmp_pos + 2)) & 0xFF
    emit(b"\x85\xc0")                            # test eax, eax
    jz32("skip")                                 # bez backslashe nic nedelame
    emit(b"\xc6\x00\x00")                        # mov byte [eax], 0  (usekni jmeno exe)
    # GetModuleHandleA("KERNEL32.dll")
    emit(b"\x8d\x83" + struct.pack("<I", KERNEL32_NAME_VA))   # lea eax,[ebx+name]
    emit(b"\x50")                                # push eax
    emit(b"\x8d\x83" + struct.pack("<I", IAT_GetModuleHandleA))
    emit(b"\x8b\x00\xff\xd0")                    # mov eax,[eax]; call eax
    emit(b"\x85\xc0")                            # test eax, eax
    jz32("skip")
    # GetProcAddress(h, "SetCurrentDirectoryA")
    str_fix = len(code) + 2                      # imm32 v lea ecx nize
    emit(b"\x8d\x8b\x00\x00\x00\x00")            # lea ecx, [ebx+STR] (VA dopocitam)
    emit(b"\x51")                                # push ecx (lpProcName)
    emit(b"\x50")                                # push eax (hModule)
    emit(b"\x8d\x83" + struct.pack("<I", IAT_GetProcAddress))
    emit(b"\x8b\x00\xff\xd0")
    emit(b"\x85\xc0")                            # test eax, eax
    jz32("skip")
    # SetCurrentDirectoryA(buf) - esp ted ukazuje na buf
    emit(b"\x54")                                # push esp
    emit(b"\xff\xd0")                            # call eax
    mark("skip")
    emit(b"\x81\xc4\x04\x01\x00\x00")            # add esp, 0x104
    emit(b"\x8d\x83" + struct.pack("<I", ORIG_EP_VA))  # lea eax,[ebx+origEP]
    emit(b"\x5d\x5f\x5e\x5b")                    # pop ebp, edi, esi, ebx
    jmp_eax_off = len(code)
    emit(b"\xff\xe0")                            # jmp eax
    str_off = len(code)
    emit(b"SetCurrentDirectoryA\x00")
    struct.pack_into("<I", code, str_fix, cave_va + str_off)
    for pos, label in fixups:
        struct.pack_into("<i", code, pos, labels[label] - (pos + 4))
    return bytes(code), jmp_eax_off


def patch(inp, out, force=False):
    import pefile

    data = bytearray(Path(inp).read_bytes())
    sha = hashlib.sha256(data).hexdigest()
    print(f"Vstup: {inp} ({len(data)} B) sha256 {sha[:16]}...")
    if sha != EXPECTED_SHA256 and not force:
        print("CHYBA: jiná verze Vampire.exe, než na kterou byl patch odladěný "
              f"(čekané sha256 {EXPECTED_SHA256[:16]}...). Pokračovat jen s --force.")
        return 1

    pe = pefile.PE(data=bytes(data), fast_load=False)
    ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
    if IMAGE_BASE + ep != ORIG_EP_VA:
        print(f"CHYBA: neočekávaný entry point 0x{IMAGE_BASE + ep:x}")
        return 1
    sect = pe.sections[0]
    assert sect.Name.rstrip(b"\0") == b".text"
    cave = bytes(data[CAVE_FILE_OFF:CAVE_FILE_OFF + CAVE_SIZE])
    if set(cave) > {0}:
        print("CHYBA: code cave na konci .text není prázdná - patch ruším.")
        return 1
    if data[KERNEL32_NAME_VA - IMAGE_BASE:KERNEL32_NAME_VA - IMAGE_BASE + 12] != b"KERNEL32.dll":
        print("CHYBA: na očekávaném místě není řetězec KERNEL32.dll.")
        return 1
    for iat, name in ((IAT_GetModuleFileNameA, "GetModuleFileNameA"),
                      (IAT_GetModuleHandleA, "GetModuleHandleA"),
                      (IAT_GetProcAddress, "GetProcAddress")):
        hint_rva = struct.unpack_from("<I", data, iat - IMAGE_BASE)[0]
        nm = bytes(data[hint_rva + 2:data.find(b"\x00", hint_rva + 2)]).decode()
        if nm != name:
            print(f"CHYBA: IAT 0x{iat:x} ukazuje na {nm!r}, čekal jsem {name!r}.")
            return 1

    stub, jmp_eax_off = build_stub(IMAGE_BASE + CAVE_RVA)
    assert len(stub) <= CAVE_SIZE, f"stub {len(stub)} B se nevejde do cave {CAVE_SIZE} B"
    print(f"Stub: {len(stub)} B (cave {CAVE_SIZE} B) @ VA 0x{IMAGE_BASE + CAVE_RVA:x}")

    # 1) stub do cave
    data[CAVE_FILE_OFF:CAVE_FILE_OFF + len(stub)] = stub
    # 2) .text VirtualSize -> SizeOfRawData (aby byl slack mapovaný)
    struct.pack_into("<I", data, sect.get_file_offset() + 8, TEXT_NEW_VSIZE)
    # 3) AddressOfEntryPoint -> cave
    ep_off = pe.OPTIONAL_HEADER.get_file_offset() + 16
    struct.pack_into("<I", data, ep_off, CAVE_RVA)

    Path(out).write_bytes(bytes(data))
    print(f"Zapsáno: {out} ({len(data)} B) sha256 {hashlib.sha256(data).hexdigest()[:16]}...")
    return verify(inp, out, stub, jmp_eax_off, ep_off, sect.get_file_offset() + 8)


def verify(orig_path, patched_path, stub, jmp_eax_off, ep_off, vsize_off):
    import pefile
    import capstone

    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  [OK] " if cond else "  [!!] ") + msg)
        ok = ok and bool(cond)

    print("Ověření patche:")
    orig = Path(orig_path).read_bytes()
    new = Path(patched_path).read_bytes()
    check(len(orig) == len(new), "velikost souboru se nezměnila")
    diff = {i for i in range(len(orig)) if orig[i] != new[i]}
    allowed = set(range(CAVE_FILE_OFF, CAVE_FILE_OFF + len(stub))) \
        | set(range(ep_off, ep_off + 4)) | set(range(vsize_off, vsize_off + 4))
    extra = diff - allowed
    check(not extra, f"rozdíly jen na povolených místech (EP, VSize, cave); navíc: "
                     f"{sorted(hex(x) for x in extra)[:5]}")
    pe = pefile.PE(data=new)
    check(pe.OPTIONAL_HEADER.AddressOfEntryPoint == CAVE_RVA, "entry point = stub")
    check(pe.sections[0].Misc_VirtualSize == TEXT_NEW_VSIZE, ".text VirtualSize zarovnaná")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    cave_va = IMAGE_BASE + CAVE_RVA
    insns = list(md.disasm(new[CAVE_FILE_OFF:CAVE_FILE_OFF + len(stub)], cave_va))
    n_bytes = sum(i.size for i in insns)
    # instrukce konci jmp eax; za ni jsou data (string) - disasm se muze splest, kontrolujeme prefix
    code_insns = []
    acc = 0
    for i in insns:
        code_insns.append(i)
        acc += i.size
        if acc >= jmp_eax_off + 2:
            break
    check(acc == jmp_eax_off + 2, f"stub se cely disasembluje ({acc} B kodu)")
    check(code_insns[-1].mnemonic == "jmp" and code_insns[-1].op_str == "eax",
          "poslední instrukce stubu je jmp eax (návrat na původní EP)")
    calls = sum(1 for i in code_insns if i.mnemonic == "call" and i.op_str == "eax")
    check(calls == 4, f"4 volání Win32 API přes call eax (nalezeno {calls})")
    str_ok = new[CAVE_FILE_OFF + len(stub) - 21:CAVE_FILE_OFF + len(stub)] == b"SetCurrentDirectoryA\x00"
    check(str_ok, "řetězec SetCurrentDirectoryA na konci stubu")
    for i in code_insns:
        print(f"    0x{i.address:x}: {i.mnemonic:8s} {i.op_str}")
    print("VÝSLEDEK:", "OK" if ok else "SELHALO - VÝSTUP NEPOUŽÍVAT")
    return 0 if ok else 2


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    inp = Path(args[0]) if args else Path("Vampire.exe")
    out = Path("Vampire_portable.exe")
    if "-o" in sys.argv:
        out = Path(sys.argv[sys.argv.index("-o") + 1])
    if not inp.is_file():
        print(f"CHYBA: vstupní soubor {inp} neexistuje.")
        return 1
    if inp.resolve() == out.resolve():
        print("CHYBA: výstup nesmí přepsat originál.")
        return 1
    return patch(inp, out, force)


if __name__ == "__main__":
    sys.exit(main())
