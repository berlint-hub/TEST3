#!/usr/bin/env python3
# Extrakce souboru cestiny z instalatoru "Vampire The Masquerade - Cz Patch 1.0 Full"
# (Vampire1.0Full.exe -- fanouskovsky cesky preklad hry Vampire: The Masquerade - Redemption).
#
# Format (zrekonstruovano analýzou, bez spousteni EXE):
#
#   Vampire1.0Full.exe
#   +-- PE stub (Delphi aplikace, UPX 1.x zabalena) ......... instalator
#   +-- overlay za posledni PE sekci (0x37400) .............. data
#       [0]    '&' ........................ priznak "komprimovano" (HKStreams)
#       [1..4] u32 LE ..................... OrigSize (velikost po dekompresi)
#       [5..]  LH5 bitstream .............. LHA -lh5- (slovnik 8 KB)
#          po dekompresi -> kontejner THKStreams (Harry Kakoulidis, v1.7):
#            8 B  01 02 03 04 05 06 07 08 . kontrolni "Goodbytes"
#            u32  pocet streamu (3)
#            zaznam: u16 delka jmena, jmeno, u32 velikost, data
#              HEAD ... titulek + BMP baner (589 878 B) + cesta v registrech
#              CRC .... prazdny (0 B)
#              DATA ... 96 souboru cestiny:
#                [u32 0]
#                zaznam: u16 delka cesty, cesta (napr. \strings\london.ntx),
#                        u32 velikost, 7 B nul, u32 velikost (znovu), obsah
#
# Pouziti:  python3 tools/extract_vampire_czpatch.py [Vampire1.0Full.exe] [-o VYSTUPNI_SLOZKA]
# Vstupni soubor se nemodifikuje; UPX stub se nemusi rozbalovat (data jsou overlay).

import argparse
import hashlib
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------- LH5 dekoder
# Verny preklad dekompresni casti HKStreamRoutines.pas (lh5unit.pas,
# Haruhiko Okumura / Haruyasu Yoshizaki, port Gregory L. Bullock).

UCHARMAX = 255
DICBIT = 13
DICSIZ = 1 << DICBIT
MATCHBIT = 8
MAXMATCH = 1 << MATCHBIT
THRESHOLD = 3
NC = UCHARMAX + MAXMATCH + 2 - THRESHOLD   # 510
CBIT = 9
NP = DICBIT + 1                            # 14
NT = 16 + 3                                # 19
PBIT = 4
TBIT = 5
NPT = NT
BITBUFSIZ = 16


class Corrupt(Exception):
    pass


class BitReader:
    """16bitovy MSB-first ctec bitu, semanticky totozny s FillBuf/GetBits."""

    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos
        self.n = len(data)
        self.BitBuf = 0
        self.SubBitBuf = 0
        self.BitCount = 0
        self.CompSize = self.n - pos
        self.FillBuf(BITBUFSIZ)

    def GetC(self):
        if self.pos < self.n:
            b = self.data[self.pos]
            self.pos += 1
            return b
        return 0

    def FillBuf(self, n):
        self.BitBuf = (self.BitBuf << n) & 0xFFFF
        while n > self.BitCount:
            n -= self.BitCount
            self.BitBuf |= (self.SubBitBuf << n) & 0xFFFF
            if self.CompSize != 0:
                self.CompSize -= 1
                self.SubBitBuf = self.GetC()
            else:
                self.SubBitBuf = 0
            self.BitCount = 8
        self.BitCount -= n
        self.BitBuf = (self.BitBuf | (self.SubBitBuf >> self.BitCount)) & 0xFFFF

    def GetBits(self, n):
        r = self.BitBuf >> (BITBUFSIZ - n)
        self.FillBuf(n)
        return r


def MakeTable(nchar, BitLen, TableBits):
    count = [0] * 18
    start = [0] * 18
    weight = [0] * 18
    for i in range(nchar):
        count[BitLen[i]] = (count[BitLen[i]] + 1) & 0xFFFF
    start[1] = 0
    for i in range(1, 17):
        start[i + 1] = (start[i] + ((count[i] << (16 - i)) & 0xFFFF)) & 0xFFFF
    if start[17] != 0:
        raise Corrupt('Compressed file is corrupt (MakeTable)')
    jutbits = 16 - TableBits
    for i in range(1, TableBits + 1):
        start[i] >>= jutbits
        weight[i] = 1 << (TableBits - i)
    for i in range(TableBits + 1, 17):
        weight[i] = 1 << (16 - i)
    Table = [0] * (1 << TableBits)
    Left = [0] * (2 * NC)
    Right = [0] * (2 * NC)
    Avail = nchar
    mask = 1 << (15 - TableBits)
    for ch in range(nchar):
        Len = BitLen[ch]
        if Len == 0:
            continue
        k = start[Len]
        nextCode = k + weight[Len]
        if Len <= TableBits:
            for j in range(k, nextCode):
                Table[j] = ch
        else:
            ref = ('T', (k >> jutbits) & 0xFFFF)

            def get(ref):
                t, idx = ref
                return Table[idx] if t == 'T' else (Left[idx] if t == 'L' else Right[idx])

            def put(ref, v):
                t, idx = ref
                if t == 'T':
                    Table[idx] = v
                elif t == 'L':
                    Left[idx] = v
                else:
                    Right[idx] = v

            i2 = Len - TableBits
            kk = k
            while i2 != 0:
                if get(ref) == 0:
                    Right[Avail] = 0
                    Left[Avail] = 0
                    put(ref, Avail)
                    Avail += 1
                ref = ('R' if (kk & mask) else 'L', get(ref))
                kk = (kk << 1) & 0xFFFF
                i2 -= 1
            put(ref, ch)
        start[Len] = nextCode
    return Table, Left, Right


class LH5:
    def __init__(self, data, pos=0):
        self.br = BitReader(data, pos)
        self.BlockSize = 0
        self.PtLen = [0] * NPT
        self.PtTable = [0] * 256
        self.PtL = self.PtR = None
        self.CLen = [0] * NC
        self.CTable = [0] * 4096
        self.CL = self.CR = None

    def ReadPtLen(self, nn, nBit, ispecial):
        br = self.br
        n = br.GetBits(nBit)
        if n == 0:
            c = br.GetBits(nBit)
            for i in range(nn):
                self.PtLen[i] = 0
            self.PtTable = [c] * 256
            self.PtL = [0] * (2 * NC)
            self.PtR = [0] * (2 * NC)
        else:
            i = 0
            while i < n:
                c = br.BitBuf >> (BITBUFSIZ - 3)
                if c == 7:
                    mask = 1 << (BITBUFSIZ - 4)
                    while mask & br.BitBuf:
                        mask >>= 1
                        c += 1
                br.FillBuf(3 if c < 7 else c - 3)
                self.PtLen[i] = c
                i += 1
                if i == ispecial:
                    c = br.GetBits(2) - 1
                    while c >= 0:
                        self.PtLen[i] = 0
                        i += 1
                        c -= 1
            while i < nn:
                self.PtLen[i] = 0
                i += 1
            self.PtTable, self.PtL, self.PtR = MakeTable(nn, self.PtLen, 8)

    def ReadCLen(self):
        br = self.br
        n = br.GetBits(CBIT)
        if n == 0:
            c = br.GetBits(CBIT)
            self.CLen = [0] * NC
            self.CTable = [c] * 4096
            self.CL = [0] * (2 * NC)
            self.CR = [0] * (2 * NC)
        else:
            i = 0
            while i < n:
                c = self.PtTable[br.BitBuf >> (BITBUFSIZ - 8)]
                if c >= NT:
                    mask = 1 << (BITBUFSIZ - 9)
                    while True:
                        c = self.PtR[c] if (br.BitBuf & mask) else self.PtL[c]
                        mask >>= 1
                        if c < NT:
                            break
                br.FillBuf(self.PtLen[c])
                if c <= 2:
                    if c == 1:
                        c = 2 + br.GetBits(4)
                    elif c == 2:
                        c = 19 + br.GetBits(CBIT)
                    while c >= 0:
                        self.CLen[i] = 0
                        i += 1
                        c -= 1
                else:
                    self.CLen[i] = c - 2
                    i += 1
            while i < NC:
                self.CLen[i] = 0
                i += 1
            self.CTable, self.CL, self.CR = MakeTable(NC, self.CLen, 12)

    def DecodeC(self):
        br = self.br
        if self.BlockSize == 0:
            self.BlockSize = br.GetBits(16)
            self.ReadPtLen(NT, TBIT, 3)
            self.ReadCLen()
            self.ReadPtLen(NP, PBIT, -1)
        self.BlockSize -= 1
        j = self.CTable[br.BitBuf >> (BITBUFSIZ - 12)]
        if j >= NC:
            mask = 1 << (BITBUFSIZ - 13)
            while True:
                j = self.CR[j] if (br.BitBuf & mask) else self.CL[j]
                mask >>= 1
                if j < NC:
                    break
        br.FillBuf(self.CLen[j])
        return j

    def DecodeP(self):
        br = self.br
        j = self.PtTable[br.BitBuf >> (BITBUFSIZ - 8)]
        if j >= NP:
            mask = 1 << (BITBUFSIZ - 9)
            while True:
                j = self.PtR[j] if (br.BitBuf & mask) else self.PtL[j]
                mask >>= 1
                if j < NP:
                    break
        br.FillBuf(self.PtLen[j])
        if j != 0:
            j -= 1
            j = (1 << j) + br.GetBits(j)
        return j

    def decode(self, out_size):
        out = bytearray()
        while len(out) < out_size:
            c = self.DecodeC()
            if c <= UCHARMAX:
                out.append(c)
            else:
                length = c - (UCHARMAX + 1 - THRESHOLD)
                src = len(out) - (self.DecodeP() + 1)
                if src < 0:
                    raise Corrupt('match pred zacatkem vystupu')
                for k in range(length):
                    out.append(out[src + k])
        return bytes(out)


# ------------------------------------------------------------------ parsovani

def pe_overlay_offset(exe):
    """Offset dat za posledni PE sekci (pro UPX soubor = konec zabaleneho PE)."""
    if exe[:2] != b'MZ':
        raise ValueError('neni MZ/PE soubor')
    pe = struct.unpack_from('<I', exe, 0x3C)[0]
    if exe[pe:pe + 4] != b'PE\x00\x00':
        raise ValueError('chybi PE podpis')
    nsec = struct.unpack_from('<H', exe, pe + 6)[0]
    opthdr = struct.unpack_from('<H', exe, pe + 20)[0]
    off = pe + 24 + opthdr
    end = 0
    for _ in range(nsec):
        rsize, rptr = struct.unpack_from('<II', exe, off + 16)
        end = max(end, rptr + rsize)
        off += 40
    return end


def read_str(buf, pos):
    """Delphi retezec s u16 delkou (THKStreams.ReadStr)."""
    ln = struct.unpack_from('<H', buf, pos)[0]
    pos += 2
    s = buf[pos:pos + ln]
    return s.decode('cp1250'), pos + ln


def parse_hk_container(blob):
    if blob[:8] != bytes([1, 2, 3, 4, 5, 6, 7, 8]):
        raise Corrupt('chybi Goodbytes 01..08 -- dekomprese se nepodarila')
    count = struct.unpack_from('<i', blob, 8)[0]
    pos = 12
    streams = {}
    for _ in range(count):
        name, pos = read_str(blob, pos)
        size = struct.unpack_from('<i', blob, pos)[0]
        pos += 4
        streams[name] = blob[pos:pos + size]
        pos += size
    if pos != len(blob):
        raise Corrupt(f'parsovani neskoncilo na konci ({pos} != {len(blob)})')
    return streams


def parse_data_records(data):
    """DATA stream: [u32 0] + zaznamy (cesta, velikost, 7x00, velikost, obsah)."""
    if struct.unpack_from('<I', data, 0)[0] != 0:
        raise Corrupt('DATA: neocekavana hlavicka')
    pos = 4
    files = []
    while pos < len(data):
        name, pos = read_str(data, pos)
        f1, mid, f2 = struct.unpack_from('<I7sI', data, pos)
        pos += 15
        content = data[pos:pos + f2]
        pos += f2
        if len(content) != f2:
            raise Corrupt(f'DATA: {name} useknuty obsah')
        files.append((name, content))
    if pos != len(data):
        raise Corrupt(f'DATA: parsovani neskoncilo na konci ({pos} != {len(data)})')
    return files


def safe_relpath(winpath):
    parts = [p for p in winpath.replace('\\', '/').split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise Corrupt(f'nebezpecna cesta: {winpath!r}')
    return Path(*parts)


def main():
    ap = argparse.ArgumentParser(description='Rozbali soubory cestiny z Vampire1.0Full.exe (bez jeho spusteni).')
    ap.add_argument('exe', nargs='?', default='Vampire1.0Full.exe')
    ap.add_argument('-o', '--out', default='Vampire1.0Full_extracted')
    a = ap.parse_args()

    exe = Path(a.exe).read_bytes()
    print(f'vstup: {a.exe} ({len(exe)} B, sha256 {hashlib.sha256(exe).hexdigest()})')

    ov = pe_overlay_offset(exe)
    flag = exe[ov:ov + 1]
    orig_size = struct.unpack_from('<I', exe, ov + 1)[0]
    print(f'overlay @ 0x{ov:x}: flag={flag!r} OrigSize={orig_size}')
    if flag != b'&':
        raise Corrupt("ocekavan priznak '&' (komprimovano)")

    blob = LH5(exe, ov + 5).decode(orig_size)
    print(f'LH5 dekomprese OK: {len(blob)} B')

    streams = parse_hk_container(blob)
    print('THKStreams streamy:', {k: len(v) for k, v in streams.items()})

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []

    # HEAD: titulek + BMP baner + cesta v registrech
    head = streams['HEAD']
    title, p = read_str(head, 2)           # prvni u16 je 0
    bfsize = struct.unpack_from('<I', head, p + 2)[0]
    banner = head[p:p + bfsize]
    if banner[:2] == b'BM':
        (out / 'installer_banner.bmp').write_bytes(banner)
        manifest.append(('installer_banner.bmp', banner))
    try:
        regpath, _ = read_str(head, p + bfsize)
    except Exception:
        regpath = ''
    (out / 'HEAD_info.txt').write_text(
        f'{title}\nRegistry (INSTALLDIR hry): HKEY_LOCAL_MACHINE\\{regpath}\n',
        encoding='utf-8')

    # DATA: samotne soubory cestiny
    files = parse_data_records(streams['DATA'])
    for winpath, content in files:
        rel = safe_relpath(winpath)
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        manifest.append((str(rel), content))

    with open(out / 'MANIFEST.txt', 'w', encoding='utf-8') as f:
        f.write(f'{title} -- obsah instalatoru rozbaleny ze souboru {a.exe}\n')
        f.write('Soubory cestiny patri do korene instalace hry Vampire: The Masquerade - Redemption\n')
        f.write('(cesty jsou relativni vuci slozce hry).\n\n')
        for rel, content in manifest:
            f.write(f'{len(content):9d}  {hashlib.sha256(content).hexdigest()}  {rel}\n')

    total = sum(len(c) for _, c in manifest)
    print(f'extrahovano: {len(manifest)} souboru ({total} B) do {out}/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
