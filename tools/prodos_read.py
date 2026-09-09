#!/usr/bin/env python3
"""Relire une image ProDOS : l'inverse de mkvolume.py, en cinquante lignes.

Sert au test de l'ecrivain (aller-retour octet a octet) et au controle d'une
image publiee : `python3 tools/prodos_read.py dist/A2FILECMD-6502.po` liste ce
qu'elle contient, comme le ferait un CATALOG.
"""
import sys
from pathlib import Path

BLOCK = 512
ENTRY_LEN = 39
TYPES = {0x04: 'TXT', 0x06: 'BIN', 0x0F: 'DIR', 0xFA: 'INT', 0xFC: 'BAS', 0xFF: 'SYS'}


class Image:
    def __init__(self, data):
        self.d = data

    def block(self, n):
        return self.d[n * BLOCK:(n + 1) * BLOCK]

    def header(self):
        e = self.block(2)[4:4 + ENTRY_LEN]
        return dict(name=e[1:1 + (e[0] & 15)].decode('ascii'),
                    files=int.from_bytes(e[0x21:0x23], 'little'),
                    bitmap=int.from_bytes(e[0x23:0x25], 'little'),
                    blocks=int.from_bytes(e[0x25:0x27], 'little'))

    def entries(self, key, skip_header=True):
        """Les entrees vivantes d'un repertoire, en suivant le chainage."""
        out, block, first = [], key, True
        while block:
            b = self.block(block)
            for k in range(13):
                if first and k == 0 and skip_header:
                    pass
                else:
                    e = b[4 + k * ENTRY_LEN:4 + (k + 1) * ENTRY_LEN]
                    if e[0] >> 4:
                        out.append(e)
            first = False
            block = int.from_bytes(b[2:4], 'little')
        return out

    def read(self, entry):
        storage = entry[0] >> 4
        key = int.from_bytes(entry[0x11:0x13], 'little')
        eof = int.from_bytes(entry[0x15:0x18], 'little')
        if storage == 1:
            return self.block(key)[:eof]
        if storage in (2, 3):
            out = bytearray()
            for n in range((eof + BLOCK - 1) // BLOCK):
                index = self.block(key)
                if storage == 3:             # l'index maitre, puis l'arbrisseau
                    index = self.block(index[n >> 8] | (index[256 + (n >> 8)] << 8))
                out += self.block(index[n & 255] | (index[256 + (n & 255)] << 8))
            return bytes(out[:eof])
        raise ValueError(f'storage type {storage} non gere')

    def free_blocks(self):
        h = self.header()
        bits = self.d[h['bitmap'] * BLOCK:]
        return sum(1 for b in range(h['blocks']) if (bits[b >> 3] >> (7 - (b & 7))) & 1)

    def walk(self, key=2, prefix=''):
        for e in self.entries(key):
            name = e[1:1 + (e[0] & 15)].decode('ascii')
            if e[0] >> 4 == 0xD:
                yield prefix + '/' + name, 'DIR', 0
                yield from self.walk(int.from_bytes(e[0x11:0x13], 'little'), prefix + '/' + name)
            else:
                yield (prefix + '/' + name, TYPES.get(e[0x10], f'${e[0x10]:02X}'),
                       int.from_bytes(e[0x15:0x18], 'little'))


def main():
    img = Image(Path(sys.argv[1]).read_bytes())
    h = img.header()
    print(f"/{h['name']}  {h['blocks']} blocs, {img.free_blocks()} libres")
    for path, kind, size in img.walk():
        print(f'  {path:<34} {kind:<4} {size if kind != "DIR" else "":>8}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
