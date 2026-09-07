#!/usr/bin/env python3
"""Etire un volume ProDOS construit par build_prodos_volume en disquette
5,25 pouces de 280 blocs, et l'ecrit en ordre ProDOS (.po) et DOS 3.3 (.dsk).

    make_floppy.py VOLUME.po SORTIE.po SORTIE.dsk

build_prodos_volume taille ses volumes au contenu, avec une marge de 64 blocs
au moins : ici on porte total_blocks a 280, on libere les blocs ajoutes dans
la table d'allocation et l'on complete a 143 360 octets. Les deux premiers
blocs (amorce ProDOS) et la table tiennent deja dans un bloc : rien d'autre
ne bouge. Le .dsk range les secteurs dans l'ordre physique de DOS 3.3, celui
que lisent ADTPro et la plupart des emulateurs pour une disquette.
"""
import sys
from pathlib import Path

BLOCKS = 280
SIZE = BLOCKS * 512
# Ordre DOS 3.3 : le bloc ProDOS b occupe, sur la piste b // 8, les secteurs
# physiques ci-dessous (deux par bloc, moitie basse puis moitie haute).
SECTORS = [(0x0, 0xE), (0xD, 0xC), (0xB, 0xA), (0x9, 0x8), (0x7, 0x6), (0x5, 0x4), (0x3, 0x2), (0x1, 0xF)]


def stretch(volume):
    v = bytearray(volume)
    total = int.from_bytes(v[2 * 512 + 4 + 0x25:2 * 512 + 4 + 0x27], 'little')
    bitmap = int.from_bytes(v[2 * 512 + 4 + 0x23:2 * 512 + 4 + 0x25], 'little')
    if total > BLOCKS:
        raise SystemExit(f'{total} blocs : le contenu ne tient pas sur une disquette de {BLOCKS}')
    if len(v) < SIZE:
        v.extend(bytes(SIZE - len(v)))
    v[2 * 512 + 4 + 0x25:2 * 512 + 4 + 0x27] = BLOCKS.to_bytes(2, 'little')
    for b in range(total, BLOCKS):
        v[bitmap * 512 + b // 8] |= 0x80 >> (b % 8)
    return bytes(v[:SIZE]), total


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
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    po, used = stretch(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(po)
    Path(sys.argv[3]).write_bytes(to_dsk(po))
    print(f'disquette : {BLOCKS} blocs, {used} occupes par le contenu, {BLOCKS - used} libres')


if __name__ == '__main__':
    main()
