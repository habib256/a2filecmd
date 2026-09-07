#!/usr/bin/env python3
"""Range une image de disquette ProDOS dans l'ordre de secteurs DOS 3.3.

    po2dsk.py ENTREE.po SORTIE.dsk

Les deux fichiers contiennent les memes 143 360 octets : seul l'ordre des
secteurs sur la piste change. Le .po est l'ordre ProDOS, le .dsk celui que
lisent ADTPro et la plupart des emulateurs quand on leur donne une disquette
5,25 pouces. Publier les deux evite a l'utilisateur d'avoir a savoir lequel
son outil attend.
"""
import sys
from pathlib import Path

BLOCKS = 280
SIZE = BLOCKS * 512
# Le bloc ProDOS b occupe, sur la piste b // 8, ces deux secteurs physiques
# (moitie basse puis moitie haute).
SECTORS = [(0x0, 0xE), (0xD, 0xC), (0xB, 0xA), (0x9, 0x8),
           (0x7, 0x6), (0x5, 0x4), (0x3, 0x2), (0x1, 0xF)]


def to_dsk(po):
    out = bytearray(SIZE)
    for block in range(BLOCKS):
        track, pair = divmod(block, 8)
        for half, sector in enumerate(SECTORS[pair]):
            src = block * 512 + half * 256
            dst = (track * 16 + sector) * 256
            out[dst:dst + 256] = po[src:src + 256]
    return bytes(out)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    po = Path(sys.argv[1]).read_bytes()
    if len(po) != SIZE:
        raise SystemExit(f'{sys.argv[1]} : {len(po)} octets, une disquette en fait {SIZE}')
    Path(sys.argv[2]).write_bytes(to_dsk(po))
    print(f'{sys.argv[2]} : {BLOCKS} blocs en ordre DOS 3.3')
    return 0


if __name__ == '__main__':
    sys.exit(main())
