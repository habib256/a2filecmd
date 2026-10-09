#!/usr/bin/env python3
"""Read-only DOS 3.3 corpus access for format studies and real-file tests.

No source writes or output-file creation. Bound all sectors and chains;
reject loops, unsupported layouts and lengths beyond the allocated data.
"""
from pathlib import Path
from take1_ref import DosImage


def dos_files(data):
    disk = DosImage(data)
    v = disk.sector(17, 0)
    if v[0x34:0x38] != bytes([35, 16, 0, 1]):
        raise ValueError('unsupported DOS geometry')
    t, s = v[1:3]
    seen = set()
    while t or s:
        if (t, s) in seen:
            raise ValueError('cyclic DOS directory')
        seen.add((t, s));cat = disk.sector(t, s)
        for i in range(7):
            e = cat[11 + 35*i:46 + 35*i]
            if e[0] in (0, 255):
                continue
            name = bytes(c & 127 for c in e[3:33]).decode('ascii').rstrip()
            tt, ss = e[:2]
            blocks, visited = [], set()
            while tt or ss:
                if (tt, ss) in visited:
                    raise ValueError('cyclic DOS T/S list')
                visited.add((tt, ss));ts = disk.sector(tt, ss)
                offset = int.from_bytes(ts[5:7], 'little')
                if offset != len(blocks):
                    raise ValueError('non-sequential DOS T/S list')
                for k in range(122):
                    a, b = ts[12 + k*2:14 + k*2]
                    blocks.append(disk.sector(a, b) if a or b else bytes(256))
                tt, ss = ts[1:3]
            body = b''.join(blocks)
            kind = e[2] & 127
            if kind == 4:
                aux = int.from_bytes(body[:2], 'little')
                size = int.from_bytes(body[2:4], 'little')
                if len(body) < 4 + size:
                    raise ValueError('short DOS binary')
                body, prodos = body[4:4 + size], 6
            elif kind in (1, 2):
                size = int.from_bytes(body[:2], 'little')
                if len(body) < 2 + size:
                    raise ValueError('short DOS BASIC/source')
                body, prodos, aux = body[2:2 + size], 0xfa if kind == 1 else 0xfc, 0
            elif kind == 0x40:
                # Alternate B / LISA v2 has its own four-byte header.
                size = int.from_bytes(body[2:4], 'little') + 5
                if len(body) < size:
                    raise ValueError('short alternate-B file')
                body, prodos, aux = body[:size], 0xf4, 0
            elif kind == 0:
                body, prodos, aux = body.split(b'\0', 1)[0], 4, 0
            else:
                continue
            yield name, prodos, aux, body
        t, s = cat[1:3]


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('disk', type=Path)
    args = ap.parse_args()
    for name, kind, aux, body in dos_files(args.disk.read_bytes()):
        print(f'{name:30} ${kind:02X}/${aux:04X} {len(body):6}')
