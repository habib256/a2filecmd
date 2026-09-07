#!/usr/bin/env python3
"""Convertit les captures PPM des bancs en PNG, sans dependance.

    ppm2png.py capture.ppm [capture.png]

POM2 rend l'ecran en PPM binaire (P6), un point par pixel de l'Apple II,
donc deux fois trop large pour un oeil habitue aux pixels carres : les lignes
sont doublees a la conversion (voir upright). Un PNG, c'est le meme tableau
de pixels precede d'un octet de filtre par ligne, le tout deflate : trente
lignes de Python suffisent, et le depot n'a besoin de rien installer pour
publier ses copies d'ecran.
"""
import struct
import sys
import zlib
from pathlib import Path


def read_ppm(data):
    """P6 : magie, largeur, hauteur, maximum, puis les octets RVB."""
    fields, pos = [], 2
    while len(fields) < 3:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':                  # un commentaire
            while data[pos:pos + 1] not in (b'\n', b''):
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(int(data[start:pos]))
    w, h, maxval = fields
    assert data[:2] == b'P6' and maxval == 255, 'PPM binaire 8 bits attendu'
    return w, h, data[pos + 1:pos + 1 + w * h * 3]


def upright(w, h, rgb):
    """Les points de l'Apple II ne sont pas carres : 560 (ou 280 en HGR
    simple) points de large pour 192 lignes, sur un ecran 4:3. Tel quel, un
    PNG sort deux fois trop large. Chaque ligne est donc doublee, et chaque
    colonne d'une page HGR simple aussi : toutes les captures font 560 x 384."""
    rows = [rgb[y * w * 3:(y + 1) * w * 3] for y in range(h)]
    if w == 280:
        rows = [b''.join(r[x * 3:x * 3 + 3] * 2 for x in range(w)) for r in rows]
        w *= 2
    return w, h * 2, b''.join(r + r for r in rows)


def png(w, h, rgb):
    raw = b''.join(b'\x00' + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload
                + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix('.png')
    w, h, rgb = upright(*read_ppm(src.read_bytes()))
    dst.write_bytes(png(w, h, rgb))
    print(f'{dst} : {w}x{h}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
