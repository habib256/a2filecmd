#!/usr/bin/env python3
"""Habille une image ProDOS brute (.hdv) d'un en-tete 2MG.

    wrap_2mg.py entree.hdv sortie.2mg

Le .2mg n'est pas un autre format de disque : c'est exactement les memes
blocs, precedes de 64 octets qui disent ce qu'ils sont -- ordre ProDOS,
nombre de blocs, ou commencent les donnees. C'est ce que reclament les
emulateurs qui refusent de deviner la geometrie d'un .hdv d'apres sa taille.

Reference : Apple II 2IMG specification (Sheppy / <https://apple2.org.za/
gswv/a2zine/Docs/DiskImage_2MG_Info.txt>).
"""

import struct
import sys
from pathlib import Path

HEADER_BYTES = 64
BLOCK_BYTES = 512
CREATOR = b"PO2A"          # pom2adventure : quatre caracteres, c'est la regle
FORMAT_PRODOS_ORDER = 1


def wrap(src: Path, dst: Path) -> int:
    data = src.read_bytes()
    if not data or len(data) % BLOCK_BYTES:
        raise SystemExit(f"{src}: {len(data)} octets, pas un multiple de 512")
    blocks = len(data) // BLOCK_BYTES

    header = bytearray(HEADER_BYTES)
    header[0:4] = b"2IMG"
    header[4:8] = CREATOR
    struct.pack_into("<H", header, 8, HEADER_BYTES)          # taille en-tete
    struct.pack_into("<H", header, 10, 1)                    # version
    struct.pack_into("<I", header, 12, FORMAT_PRODOS_ORDER)
    struct.pack_into("<I", header, 16, 0)                    # drapeaux
    struct.pack_into("<I", header, 20, blocks)
    struct.pack_into("<I", header, 24, HEADER_BYTES)         # debut des donnees
    struct.pack_into("<I", header, 28, len(data))
    # Commentaire et donnees du createur : absents, donc offset ET longueur a
    # zero. Un offset non nul avec une longueur nulle fait tiquer certains
    # lecteurs.

    dst.write_bytes(bytes(header) + data)
    return blocks


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: wrap_2mg.py entree.hdv sortie.2mg", file=sys.stderr)
        return 2
    blocks = wrap(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"==> {sys.argv[2]} : {blocks} blocs ProDOS "
          f"({blocks * BLOCK_BYTES // 1024} Ko) + en-tete 2MG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
