#!/usr/bin/env python3
"""Habille une image ProDOS brute (.po ou .hdv) d'un en-tete 2IMG.

    po22mg.py ENTREE.po SORTIE.2mg

Le .2mg est le format universel des emulateurs et de CiderPress : 64 octets
d'en-tete, puis les blocs dans l'ordre ProDOS, tels quels. C'est ce que lit
aussi A2 File Cmd quand on ouvre un .2MG comme un dossier.
"""
import struct
import sys
from pathlib import Path

HEADER = 64


def to_2mg(po, creator=b'A2FC'):
    if len(po) % 512:
        raise ValueError(f'{len(po)} octets : pas un multiple de 512')
    blocks = len(po) // 512
    head = struct.pack('<4s4sHHIIIIIIIII', b'2IMG', creator, HEADER, 1,
                       1,             # format 1 : ordre ProDOS
                       0,             # drapeaux (pas verrouille, pas de volume DOS)
                       blocks, HEADER, len(po),
                       0, 0, 0, 0)    # commentaire et donnees du createur : aucun
    return head.ljust(HEADER, b'\0') + po


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    po = Path(sys.argv[1]).read_bytes()
    Path(sys.argv[2]).write_bytes(to_2mg(po))
    print(f'{sys.argv[2]} : {len(po) // 512} blocs en 2IMG')
    return 0


if __name__ == '__main__':
    sys.exit(main())
