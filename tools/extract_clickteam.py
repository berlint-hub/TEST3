#!/usr/bin/env python3
"""Extraktor pro instalatery Clickteam Install Creator (2.x).

Prepis formatu podle open-source nastroje cicdec (Bioruebe, GitHub)
do cisteho Pythonu (jen stdlib). Rozbaluje bloky instalateru a z
FILE_LIST + FILE_DATA vytahuje vsechny soubory i s puvodnimi cestami.

Pouziti:
    python3 tools/extract_clickteam.py <instaler.exe> [vystupni_slozka] [--list]
"""
import bz2
import os
import struct
import sys
import zlib

SIGNATURE = bytes([0x77, 0x77, 0x67, 0x54, 0x29, 0x48])  # "wwgT)H"
BLOCK_NAMES = {
    0x143A: "FILE_LIST", 0x7F7F: "FILE_DATA", 0x143E: "STRINGS",
    0x1435: "UNKNOWN_FONT_DIALOG", 0x1436: "UNKNOWN_DATA",
    0x1437: "BACKGROUND_IMAGE", 0x1444: "UNKNOWN_NUMBERS",
    0x1445: "REGISTRY_CHANGES", 0x143F: "UNINSTALLER",
}
COMPR_NONE, COMPR_DEFLATE, COMPR_BZ2 = 0, 1, 2


def decompress(comp, method, usize):
    """Rozbali jeden blok/fragment; vrati (data, spotrebovano_vstupu_odhad)."""
    if method == COMPR_NONE:
        return comp[:usize]
    if method == COMPR_DEFLATE:
        o = zlib.decompressobj(-15)  # surove deflate; 2B zlib hlava se preskakuje
        out = o.decompress(comp[2:], usize)
        return out
    if method == COMPR_BZ2:
        return bz2.BZ2Decompressor().decompress(comp, usize)
    raise ValueError(f"neznama komprese {method:#x} (mozna sifrovano)")


class Cursor:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def u16(self):
        v, = struct.unpack_from("<H", self.buf, self.pos)
        self.pos += 2
        return v

    def u32(self):
        v, = struct.unpack_from("<I", self.buf, self.pos)
        self.pos += 4
        return v

    def i64(self):
        v, = struct.unpack_from("<q", self.buf, self.pos)
        self.pos += 8
        return v

    def byte(self):
        v = self.buf[self.pos]
        self.pos += 1
        return v

    def skip(self, n):
        self.pos += n

    def bytes(self, n):
        v = self.buf[self.pos:self.pos + n]
        self.pos += n
        return v


class Node:
    __slots__ = ("node_start", "node_size", "node_end", "type", "offset",
                 "compressed", "unknown32", "uncompressed", "index", "path")

    def __init__(self, start, size, typ):
        self.node_start, self.node_size = start, size
        self.node_end = start + size
        self.type = typ
        self.offset = self.compressed = self.unknown32 = 0
        self.uncompressed = self.index = 0
        self.path = None

    def valid(self, total_len):
        if self.node_size < 4 or self.node_end > 10 ** 9:
            return False
        if self.offset > total_len:
            return False
        if self.compressed == 0 and self.uncompressed > 3_000_000_000:
            return False
        if self.uncompressed > 10 and self.compressed > 10 \
                and self.compressed > self.uncompressed * 5:
            return False
        if self.index > 1_000_000_000:
            return False
        if self.type == 0:
            if not self.path:
                return False
            bad = set('<>:"|?*') | {chr(c) for c in range(0x20)}
            if any(ch in bad for ch in self.path):
                return False
        return True


def read_path(cur, node):
    n = node.node_end - cur.pos
    if n < 1:
        return
    raw = cur.bytes(n)
    z = raw.find(b"\x00")
    if z > -1:
        raw = raw[:z]
    node.path = raw.decode("cp1250", errors="replace")


def parse20(cur):
    nd = Node(cur.pos, cur.u32(), cur.u16())
    if nd.type != 0:
        return nd
    cur.skip(14)
    nd.uncompressed = cur.u32()
    nd.offset = cur.u32()
    nd.compressed = cur.u32()
    cur.i64(); cur.i64(); cur.i64()
    read_path(cur, nd)
    return nd


def parse24(cur):
    nd = Node(cur.pos, cur.u16(), cur.u16())
    if nd.type != 0:
        return nd
    cur.skip(2)
    nd.offset = cur.u32(); nd.compressed = cur.u32()
    nd.unknown32 = cur.u32(); nd.uncompressed = cur.u32()
    cur.skip(16)
    cur.i64(); cur.i64(); cur.i64()
    read_path(cur, nd)
    return nd


def parse30(cur):
    nd = Node(cur.pos, cur.u16(), cur.u16())
    if nd.type != 0:
        return nd
    cur.skip(2)
    nd.offset = cur.u32(); nd.compressed = cur.u32()
    nd.unknown32 = cur.u32(); nd.uncompressed = cur.u32()
    cur.skip(18)
    nd.index = cur.u32()
    cur.i64(); cur.i64(); cur.i64()
    read_path(cur, nd)
    return nd


def parse35(cur):
    nd = Node(cur.pos, cur.u32(), cur.u16())
    if nd.type != 0:
        return nd
    cur.skip(3)
    cur.skip(30 if cur.byte() == 0xE2 else 14)
    nd.uncompressed = cur.u32()
    nd.offset = cur.u32(); nd.compressed = cur.u32(); nd.unknown32 = cur.u32()
    nd.index = cur.u32()
    cur.skip(2)
    cur.i64(); cur.i64(); cur.i64()
    read_path(cur, nd)
    return nd


def parse40(cur):
    nd = Node(cur.pos, cur.u32(), cur.u16())
    if nd.type != 0:
        return nd
    cur.skip(3)
    if cur.byte() == 0xE2:          # prazdny dummy soubor
        cur.skip(30)
    else:
        cur.skip(14)
        nd.uncompressed = cur.u32()
        nd.offset = cur.u32()
        nd.compressed = cur.u32()
        cur.skip(4)
        cur.i64(); cur.i64(); cur.i64()
    read_path(cur, nd)
    return nd


PARSERS = [(40, parse40), (35, parse35), (30, parse30),
           (24, parse24), (20, parse20)]


def parse_file_list(fl_buf, total_len):
    cur = Cursor(fl_buf)
    count = cur.u16()
    cur.skip(2)
    start = cur.pos
    for version, fn in PARSERS:
        cur.pos = start
        nodes, ok = [], True
        try:
            for _ in range(count):
                nd = fn(cur)
                if not nd.valid(total_len):
                    ok = False
                    break
                nodes.append(nd)
                if nd.type != 0:
                    cur.pos = nd.node_end
        except (struct.error, IndexError):
            ok = False
        if ok:
            return version, [n for n in nodes if n.type == 0]
    raise ValueError("nepodarilo se urcit verzi formatu seznamu souboru")


def unpack_payload(d, payload_pos, block_size):
    """Standardni blok: u32 rozbalena velikost + u8 metoda + data."""
    usize, method = struct.unpack_from("<IB", d, payload_pos)
    comp = d[payload_pos + 5: payload_pos + block_size]
    return decompress(comp, method, usize), method


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    list_only = "--list" in sys.argv
    if not args:
        print(__doc__)
        return 2
    src = args[0]
    outdir = args[1] if len(args) > 1 else src + "_extracted"
    d = open(src, "rb").read()

    sig = d.find(SIGNATURE)
    if sig < 0:
        print("CHYBA: signatura Clickteam dat nenalezena")
        return 1
    print(f"datova sekce @ 0x{sig:x}")
    pos = sig + len(SIGNATURE)

    file_list = None
    data_start = None
    blocks_dir = os.path.join(outdir, "_installer_blocks")
    while pos + 8 <= len(d):
        bid, _unk, bsize = struct.unpack_from("<HHI", d, pos)
        name = BLOCK_NAMES.get(bid, "UNKNOWN")
        payload = pos + 8
        print(f"  blok 0x{bid:04x} {name:22s} @0x{payload:x} vel {bsize}")
        if bid == 0x7F7F:  # FILE_DATA byva posledni
            data_start = payload
            break
        try:
            out, method = unpack_payload(d, payload, bsize)
        except Exception as e:
            print(f"    ! rozbaleni selhalo: {e}")
            out = None
        if bid == 0x143A:
            file_list = out
        if out is not None and not list_only:
            os.makedirs(blocks_dir, exist_ok=True)
            with open(os.path.join(blocks_dir, f"0x{bid:04x}_{name}.bin"), "wb") as f:
                f.write(out)
        pos = payload + bsize

    if file_list is None or data_start is None:
        print("CHYBA: chybi FILE_LIST nebo FILE_DATA blok")
        return 1

    version, files = parse_file_list(file_list, len(d))
    print(f"\nverze formatu: {version}; souboru v instalateri: {len(files)}\n")

    failed = 0
    for i, nd in enumerate(files, 1):
        rel = nd.path.replace("\\", "/")
        print(f"  {i:2d}/{len(files)}  {nd.uncompressed:>9d} B  {rel}")
        if list_only:
            continue
        try:
            if nd.uncompressed == 0:
                out = b""
            else:
                p = data_start + nd.offset + 4
                method = d[p]
                comp = d[p + 1: p + 1 + nd.compressed]
                out = decompress(comp, method, nd.uncompressed)
            if len(out) != nd.uncompressed:
                print(f"      ! velikost sedi spatne: {len(out)} != {nd.uncompressed}")
                failed += 1
            safe = safe_output_path(outdir, rel)
            if safe is None:
                print("      ! nebezpecna cesta, preskakuji")
                failed += 1
                continue
            os.makedirs(os.path.dirname(safe), exist_ok=True)
            with open(safe, "wb") as f:
                f.write(out)
        except Exception as e:
            print(f"      ! selhalo: {e}")
            failed += 1

    print(f"\nhotovo, selhani: {failed}")
    return 1 if failed else 0


def safe_output_path(outdir, rel):
    parts = []
    for p in rel.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            return None
        if p.endswith(":") or (p.startswith("#") and p.endswith("#")):
            continue  # jednotka / makro typu #InstallDir#
        parts.append(p)
    if not parts:
        return None
    return os.path.join(outdir, *parts)


if __name__ == "__main__":
    sys.exit(main())
