#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binární patch Vampire: The Masquerade - Redemption (Vampire.exe) -> "portable" verze.

Řeší dva problémy s ukládáním (ověřeno analýzou kódu hry):

1) ŠPATNÁ SLOŽKA: hra ukládá nastavení i savy vůči pracovnímu adresáři
   procesu (masquerade.ini = GetCurrentDirectoryA + jméno, savy =
   relativní "SaveGames\\..."). Když launcher (autorun/Wine frontend)
   nastaví jiný pracovní adresář, soubory skončí jinde.
   => Stub na entry pointu hře nastaví pracovní adresář na složku,
      kde leží její EXE (GetModuleFileNameA + SetCurrentDirectoryA),
      a zároveň odemkne masquerade.ini (SetFileAttributesA NORMAL),
      aby atribut Jen-pro-čtení (z kopie z CD/ISO) neblokoval zápis.

2) ZÁPIS AŽ PŘI ČISTÉM UKONČENÍ: options hra zapisuje do
   masquerade.ini jen při řádném shutdownu:
     - render options: přes atexit() (registrace na 0x4c212a),
     - gameOptions + zvuk: v hlavní shutdown sekvenci (0x42cf70/0x42cf98).
   Když frontend proces zabije (typické pro Wine launchery), zápis
   nikdy neproběhne a options se "neukládají", přestože savy fungují
   (ty se píšou hned). => Hook: tři cesty zavření obrazovky Options
   (tlačítko Done 0x414d22, ESC/zavření 0x414c82, shutdown obrazovky
   0x414c12) nově před svým posledním krokem zavolají náš cave stub,
   který okamžitě zapíše všechny tři skupiny nastavení (stejné
   funkce, jaké hra volá při shutdownu: 0x4c2140 render, 0x427850
   gameOptions, 0x49e520 zvuk) a teprve pak pokračuje původním kódem.

Zásahy (nic jiného se nemění): AddressOfEntryPoint -> EP stub v cave
na konci .text; .text VirtualSize zarovnaná na SizeOfRawData (aby byl
slack mapovaný); 3x rel32 u hookovaných callů. Oba stuby jsou
position-independent (delta přes call/pop) a při jakékoli chybě tiše
pokračují původním tokem. Výstup je vždy Vampire_portable.exe,
originál zůstává nedotčený. Patch je ověřený staticky i emulací
(Unicorn), ale hru tu spustit nejde - originál si zazálohuj.

Použití: python3 patch_vampire_portable.py Vampire.exe [-o vystup.exe]
"""

import hashlib
import struct
import sys
from pathlib import Path

EXPECTED_SHA256 = {
    "dd647078a6bf1ed9e1f36e6fe2d37bbd7fe2e1543aca220a3b5d9302dfa2b886",  # Vampire.exe (GOG)
    "41dec009af2524aba1219f768ca311c4a09ca9973751e109009fa882696b9e49",  # Vampire_aor.exe (Age of Redemption)
}
IB = 0x400000
ORIG_EP_VA = 0x4DF343
IAT_GMFN = 0x4EB064          # GetModuleFileNameA
IAT_GMH = 0x4EB0A8           # GetModuleHandleA
IAT_GPA = 0x4EB148           # GetProcAddress
KERNEL32_NAME_VA = 0x4F1E0A  # "KERNEL32.dll" v import deskriptoru
INI_NAME_VA = 0x52DA28       # "masquerade.ini"
CAVE_RVA = 0xEAEE0
CAVE_OFF = 0xEAEE0
CAVE_SIZE = 0x120
TEXT_NEW_VSIZE = 0xEA000

SAVE_RENDER = 0x4C2140       # atexit-funkce: mov ecx,0x6a49a0; jmp SaveRenderOptions
SAVE_GAMEOPT = 0x427850      # thiscall(ecx = 0x613cb8)
SAVE_AUDIO = 0x49E520        # thiscall(ecx = audio objekt)
GAMEOPT_STRUCT = 0x613CB8
AUDIO_OBJ_PTR = 0x659C88     # *ptr na audio objekt
AUDIO_INITED = 0x659C90      # flag "audio bezi"
HOOK_ORIG = 0x402420         # puvodni cil hookovanych callu (tail krok Options teardownu)
HOOK_SITES = (0x414C12, 0x414C82, 0x414D22)


def _rel8(cur_end, target):
    d = target - cur_end
    assert -128 <= d <= 127, f"rel8 mimo dosah: {d}"
    return d & 0xFF


def build_ep_stub(cave_va):
    c = bytearray()
    labels, fix8 = {}, []

    def e(b):
        c.extend(b)

    def mark(n):
        labels[n] = len(c)

    def jz8(n):
        e(b"\x74")
        fix8.append((len(c), n))
        e(b"\x00")

    def jmp8(n):
        e(b"\xeb")
        fix8.append((len(c), n))
        e(b"\x00")

    def jne8(n):
        e(b"\x75")
        fix8.append((len(c), n))
        e(b"\x00")

    e(b"\x53\x56\x57\x55")                              # push ebx,esi,edi,ebp
    e(b"\xe8\x00\x00\x00\x00")                          # call $+5
    pop_off = len(c)
    e(b"\x5b")                                          # pop ebx
    e(b"\x81\xeb" + struct.pack("<I", cave_va + pop_off))  # sub ebx, linkVA = delta
    e(b"\x81\xec\x04\x01\x00\x00")                      # sub esp, 0x104
    e(b"\x8d\x04\x24")                                  # lea eax, [esp] (buf)
    e(b"\x68\x04\x01\x00\x00\x50\x6a\x00")               # push 0x104, push eax, push 0
    e(b"\x8b\x83" + struct.pack("<I", IAT_GMFN))        # mov eax, [ebx+IAT GetModuleFileNameA]
    e(b"\xff\xd0")                                      # call eax
    e(b"\x8d\x3c\x24")                                  # lea edi, [esp]
    e(b"\x33\xc0")                                      # xor eax, eax (posledni '\')
    mark("scan")
    e(b"\x8a\x17")                                      # mov dl, [edi]
    e(b"\x84\xd2")                                      # test dl, dl
    jz8("done")
    e(b"\x80\xfa\x5c")                                  # cmp dl, '\'
    jne8("next")
    e(b"\x8b\xc7")                                      # mov eax, edi
    mark("next")
    e(b"\x47")                                          # inc edi
    jmp8("scan")
    mark("done")
    e(b"\x85\xc0")                                      # test eax, eax
    jz8("skip")
    e(b"\xc6\x00\x00")                                  # mov byte [eax], 0
    # esi = GetModuleHandleA("KERNEL32.dll")
    e(b"\x8d\x83" + struct.pack("<I", KERNEL32_NAME_VA))
    e(b"\x50")
    e(b"\x8b\x83" + struct.pack("<I", IAT_GMH))
    e(b"\xff\xd0")
    e(b"\x85\xc0")                                      # test eax, eax
    jz8("skip")
    e(b"\x8b\xf0")                                      # mov esi, eax
    # ebp = GetProcAddress(esi, "SetCurrentDirectoryA")
    str1_fix = len(c) + 2
    e(b"\x8d\x8b\x00\x00\x00\x00")                      # lea ecx, [ebx+STR1]
    e(b"\x51\x56")                                      # push ecx, push esi
    e(b"\x8b\x83" + struct.pack("<I", IAT_GPA))
    e(b"\xff\xd0")
    e(b"\x8b\xe8")                                      # mov ebp, eax
    # eax = GetProcAddress(esi, "SetFileAttributesA")
    str2_fix = len(c) + 2
    e(b"\x8d\x8b\x00\x00\x00\x00")                      # lea ecx, [ebx+STR2]
    e(b"\x51\x56")
    e(b"\x8b\x83" + struct.pack("<I", IAT_GPA))
    e(b"\xff\xd0")
    # SetCurrentDirectoryA(buf), eax (SetFileAttributesA ptr) drzime pres push/pop
    e(b"\x50")                                          # push eax
    e(b"\x85\xed")                                      # test ebp, ebp
    jz8("nosetcd")
    e(b"\x8d\x4c\x24\x04")                              # lea ecx, [esp+4] (= buf)
    e(b"\x51")                                          # push ecx
    e(b"\xff\xd5")                                      # call ebp
    mark("nosetcd")
    e(b"\x58")                                          # pop eax
    # SetFileAttributesA("masquerade.ini", FILE_ATTRIBUTE_NORMAL=0x80)
    e(b"\x85\xc0")                                      # test eax, eax
    jz8("skip")
    e(b"\x68\x80\x00\x00\x00")                          # push 0x80
    e(b"\x8d\x8b" + struct.pack("<I", INI_NAME_VA))     # lea ecx, [ebx+"masquerade.ini"]
    e(b"\x51")                                          # push ecx
    e(b"\xff\xd0")                                      # call eax
    mark("skip")
    e(b"\x81\xc4\x04\x01\x00\x00")                      # add esp, 0x104
    e(b"\x8d\x83" + struct.pack("<I", ORIG_EP_VA))      # lea eax, [ebx+origEP]
    e(b"\x5d\x5f\x5e\x5b")                              # pop ebp,edi,esi,ebx
    jmp_eax_off = len(c)
    e(b"\xff\xe0")                                      # jmp eax
    str1_off = len(c)
    e(b"SetCurrentDirectoryA\x00")
    str2_off = len(c)
    e(b"SetFileAttributesA\x00")
    struct.pack_into("<I", c, str1_fix, cave_va + str1_off)
    struct.pack_into("<I", c, str2_fix, cave_va + str2_off)
    for pos, name in fix8:
        c[pos] = _rel8(pos + 1, labels[name])
    return bytes(c), jmp_eax_off


def build_hook_stub(hook_va):
    """SaveAllOptions + tail-jmp na puvodni cil. Vstup: zasobnik i registry
    patri puvodnimu callee (0x402420) - vse zachovame (pushad/pushfd)."""
    c = bytearray()

    def e(b):
        c.extend(b)

    def rel32(tgt):
        return struct.pack("<i", tgt - (hook_va + len(c) + 5))

    e(b"\x60")                                          # pushad
    e(b"\x9c")                                          # pushfd
    e(b"\xe8\x00\x00\x00\x00")                          # call $+5
    pop_off = len(c)
    e(b"\x5b")                                          # pop ebx
    e(b"\x81\xeb" + struct.pack("<I", hook_va + pop_off))  # ebx = delta
    e(b"\xe8" + rel32(SAVE_RENDER))                     # SaveRenderOptions()
    e(b"\x8d\x8b" + struct.pack("<I", GAMEOPT_STRUCT))  # lea ecx, [ebx+struct]
    e(b"\xe8" + rel32(SAVE_GAMEOPT))                    # SaveGameOptions()
    e(b"\x83\xbb" + struct.pack("<I", AUDIO_INITED) + b"\x00")  # cmp dword [ebx+inited], 0
    je1 = len(c)
    e(b"\x74\x00")                                      # je tail
    e(b"\x8b\x8b" + struct.pack("<I", AUDIO_OBJ_PTR))   # mov ecx, [ebx+objptr]
    e(b"\x85\xc9")                                      # test ecx, ecx
    je2 = len(c)
    e(b"\x74\x00")                                      # je tail
    e(b"\xe8" + rel32(SAVE_AUDIO))                      # SaveAudioOptions()
    tail = len(c)
    c[je1 + 1] = _rel8(je1 + 2, tail)
    c[je2 + 1] = _rel8(je2 + 2, tail)
    e(b"\x9d")                                          # popfd
    e(b"\x61")                                          # popad
    e(b"\xe9" + rel32(HOOK_ORIG))                       # jmp 0x402420 (puvodni cil)
    return bytes(c)


def patch(inp, out, force=False):
    import pefile

    data = bytearray(Path(inp).read_bytes())
    sha = hashlib.sha256(data).hexdigest()
    print(f"Vstup: {inp} ({len(data)} B) sha256 {sha[:16]}...")
    if sha not in EXPECTED_SHA256 and not force:
        print("CHYBA: jiná verze Vampire.exe, než na kterou byl patch odladěný. "
              "Pokračovat jen s --force.")
        return 1

    pe = pefile.PE(data=bytes(data), fast_load=False)
    if IB + pe.OPTIONAL_HEADER.AddressOfEntryPoint != ORIG_EP_VA:
        print("CHYBA: neočekávaný entry point.")
        return 1
    sect = pe.sections[0]
    assert sect.Name.rstrip(b"\0") == b".text"
    if set(data[CAVE_OFF:CAVE_OFF + CAVE_SIZE]) > {0}:
        print("CHYBA: code cave na konci .text není prázdná.")
        return 1
    if data[KERNEL32_NAME_VA - IB:KERNEL32_NAME_VA - IB + 12] != b"KERNEL32.dll":
        print("CHYBA: chybí řetězec KERNEL32.dll na očekávaném místě.")
        return 1
    if data[INI_NAME_VA - IB:INI_NAME_VA - IB + 15] != b"masquerade.ini\x00":
        print("CHYBA: chybí řetězec masquerade.ini na očekávaném místě.")
        return 1
    for iat, name in ((IAT_GMFN, "GetModuleFileNameA"), (IAT_GMH, "GetModuleHandleA"),
                      (IAT_GPA, "GetProcAddress")):
        hint = struct.unpack_from("<I", data, iat - IB)[0]
        nm = bytes(data[hint + 2:data.find(b"\x00", hint + 2)]).decode()
        if nm != name:
            print(f"CHYBA: IAT 0x{iat:x} = {nm!r}, čekal jsem {name!r}.")
            return 1
    for site in HOOK_SITES:
        off = site - IB
        if data[off] != 0xE8 or site + 5 + struct.unpack_from("<i", data, off + 1)[0] != HOOK_ORIG:
            print(f"CHYBA: na hook místě 0x{site:x} není call 0x{HOOK_ORIG:x}.")
            return 1

    cave_va = IB + CAVE_RVA
    ep_stub, jmp_eax_off = build_ep_stub(cave_va)
    hook_off = (len(ep_stub) + 15) & ~15
    hook_va = cave_va + hook_off
    hook_stub = build_hook_stub(hook_va)
    total = hook_off + len(hook_stub)
    assert total <= CAVE_SIZE, f"stuby {total} B > cave {CAVE_SIZE} B"
    print(f"EP stub {len(ep_stub)} B @0x{cave_va:x}, hook stub {len(hook_stub)} B "
          f"@0x{hook_va:x} (cave {CAVE_SIZE} B)")

    data[CAVE_OFF:CAVE_OFF + len(ep_stub)] = ep_stub
    data[CAVE_OFF + hook_off:CAVE_OFF + total] = hook_stub
    struct.pack_into("<I", data, sect.get_file_offset() + 8, TEXT_NEW_VSIZE)
    ep_field_off = pe.OPTIONAL_HEADER.get_file_offset() + 16
    struct.pack_into("<I", data, ep_field_off, CAVE_RVA)
    for site in HOOK_SITES:
        struct.pack_into("<i", data, site - IB + 1, hook_va - (site + 5))

    Path(out).write_bytes(bytes(data))
    print(f"Zapsáno: {out} ({len(data)} B) sha256 {hashlib.sha256(data).hexdigest()[:16]}...")
    return verify(inp, out, ep_stub, jmp_eax_off, hook_off, hook_stub,
                  ep_field_off, sect.get_file_offset() + 8)


def verify(orig_path, patched_path, ep_stub, jmp_eax_off, hook_off, hook_stub,
           ep_field_off, vsize_off):
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
    allowed = set(range(CAVE_OFF, CAVE_OFF + hook_off + len(hook_stub))) \
        | set(range(ep_field_off, ep_field_off + 4)) \
        | set(range(vsize_off, vsize_off + 4))
    for site in HOOK_SITES:
        allowed |= set(range(site - IB + 1, site - IB + 5))
    extra = diff - allowed
    check(not extra, f"rozdíly jen na povolených místech; navíc: {sorted(hex(x) for x in extra)[:5]}")
    pe = pefile.PE(data=new)
    check(pe.OPTIONAL_HEADER.AddressOfEntryPoint == CAVE_RVA, "entry point = EP stub")
    check(pe.sections[0].Misc_VirtualSize == TEXT_NEW_VSIZE, ".text VirtualSize zarovnaná")
    hook_va = IB + CAVE_RVA + hook_off
    for site in HOOK_SITES:
        rel = struct.unpack_from("<i", new, site - IB + 1)[0]
        check(site + 5 + rel == hook_va, f"hook 0x{site:x} -> cave stub 0x{hook_va:x}")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    cave_va = IB + CAVE_RVA
    ins = []
    acc = 0
    for i in md.disasm(new[CAVE_OFF:CAVE_OFF + len(ep_stub)], cave_va):
        ins.append(i)
        acc += i.size
        if acc >= jmp_eax_off + 2:
            break
    check(acc == jmp_eax_off + 2 and ins[-1].mnemonic == "jmp" and ins[-1].op_str == "eax",
          "EP stub: celý se disasembluje a končí jmp eax")
    check(sum(1 for i in ins if i.mnemonic == "call") >= 5, "EP stub: volání API/funkcí >= 5")
    for i in ins:
        print(f"    EP 0x{i.address:x}: {i.mnemonic:8s} {i.op_str}")
    ins2 = list(md.disasm(new[CAVE_OFF + hook_off:CAVE_OFF + hook_off + len(hook_stub)], hook_va))
    tot2 = sum(i.size for i in ins2)
    check(tot2 == len(hook_stub), f"hook stub: celý se disasembluje ({tot2} B)")
    check(ins2[-1].mnemonic == "jmp" and int(ins2[-1].op_str, 16) == HOOK_ORIG,
          f"hook stub: končí jmp 0x{HOOK_ORIG:x} (původní cíl)")
    calls = [int(i.op_str, 16) for i in ins2 if i.mnemonic == "call" and i.op_str.startswith("0x")]
    check(SAVE_RENDER in calls and SAVE_GAMEOPT in calls and SAVE_AUDIO in calls,
          "hook stub: volá SaveRender + SaveGameOptions + SaveAudioOptions")
    for i in ins2:
        print(f"    HK 0x{i.address:x}: {i.mnemonic:8s} {i.op_str}")
    print("VÝSLEDEK:", "OK" if ok else "SELHALO - VÝSTUP NEPOUŽÍVAT")
    return 0 if ok else 2


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    inp = Path(args[0]) if args else Path("Vampire.exe")
    out = inp.with_name(inp.stem + "_portable.exe")
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
