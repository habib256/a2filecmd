#!/usr/bin/env python3
"""Fabrique les fichiers de demonstration de la disquette A2 File Cmd.

    mkdemo.py DOSSIER

Rien n'est emprunte : tout est calcule ici, et donc redistribuable sans
question. La disquette a besoin de quoi essayer chaque visionneuse, et une
mire vaut mieux qu'une photo pour cela -- on voit tout de suite si le
decodage des couleurs est juste.

  DHGR.RLE   les seize couleurs du double haute resolution, en barres,
             compressees dans le flux DHRR v1 que lit A2 File Cmd
  HGR.RLE    les six couleurs du haute resolution simple, flux HGRR v1
  WELCOME.MB une fanfare de trois voix pour la Mockingboard, flux MB1
  SAMPLE.TXT un texte pour la visionneuse et l'editeur
  HELLO      un programme Applesoft, si BASIC.SYSTEM est sur le volume
"""
import sys
from pathlib import Path

# ── HGR et DHGR ────────────────────────────────────────────────────────────
def hgr_offset(row):
    """L'entrelacement d'Apple : la ligne `row` commence a cet octet."""
    return (row & 7) * 0x400 + ((row >> 3) & 7) * 0x80 + (row >> 6) * 0x28


def hgr_card():
    """8 192 octets : les six couleurs HGR en bandes, encadrees de blanc."""
    page = bytearray(8192)
    bands = [0x00, 0x2A, 0x55, 0x7F, 0xAA, 0xD5, 0x80]   # noir vert violet blanc orange bleu noir
    for row in range(192):
        off = hgr_offset(row)
        fill = bands[min(row * len(bands) // 192, len(bands) - 1)]
        if row < 2 or row >= 190:
            fill = 0x7F                                   # le cadre
        for x in range(40):
            page[off + x] = 0x7F if (x < 1 or x >= 39) else fill
    return bytes(page)


def dhgr_card():
    """16 384 octets, plan AUX puis plan MAIN : seize bandes horizontales, une
    valeur d'octet par bande, la meme dans les deux plans -- des aplats que le
    RLE ecrase a moins d'un kilo-octet (la mire a motifs de quatre octets en
    faisait douze : vingt-deux blocs rendus a la disquette pour les
    surcouches). Un cadre blanc ($7F) borde chaque ligne."""
    # seize valeurs distinctes, du noir ($00) au blanc ($7F) : chaque bande
    # rend un aplat ou une trame fine propre au DHGR, toutes differentes.
    bands = [0x00, 0x08, 0x11, 0x19, 0x22, 0x2A, 0x33, 0x3B,
             0x44, 0x4C, 0x55, 0x5D, 0x66, 0x6E, 0x77, 0x7F]
    aux, main = bytearray(8192), bytearray(8192)
    for row in range(192):
        off = hgr_offset(row)
        b = 0x7F if row < 3 or row >= 189 else bands[min((row - 3) * 16 // 186, 15)]
        for j in range(40):
            v = 0x7F if j == 0 or j == 39 else b
            aux[off + j] = v
            main[off + j] = v
    return bytes(aux) + bytes(main)


def rle(data):
    """Le flux v1 que decode a2fc.c : $80|n-3 puis l'octet, ou n-1 litteraux."""
    out, i, n = bytearray(), 0, len(data)
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 130:
            run += 1
        if run >= 3:
            out += bytes((0x80 | (run - 3), data[i]))
            i += run
            continue
        start = i
        while i < n:
            run = 1
            while i + run < n and data[i + run] == data[i] and run < 4:
                run += 1
            if run >= 3 or i - start == 128:
                break
            i += 1
        out += bytes((i - start - 1,)) + data[start:i]
    return bytes(out)


def image(magic, size, raw):
    assert len(raw) == size, (len(raw), size)
    head = magic + bytes((1, 0, size & 0xFF, size >> 8))
    return head + rle(raw)


# ── La musique ─────────────────────────────────────────────────────────────
# Flux MB1 : en-tete de 8 octets, puis des paquets. Un octet < $80 attend
# autant de ticks a 50 Hz ; $8v suivi d'un index de note joue sur la voix v
# ($90 la coupe, $Av regle son volume) ; $E0 termine. Index 0 = do2, un par
# demi-ton (src/ay_notes.inc).
C3, E3, G3, C4, E4, G4, C5 = 12, 16, 19, 24, 28, 31, 36


def fanfare():
    s = bytearray()
    for v, vol in ((0, 13), (1, 11), (2, 9)):
        s += bytes((0xA0 | v, vol))
    def note(voice, idx, ticks):
        s.extend((0x80 | voice, idx, ticks))
    for idx in (C3, E3, G3, C4, E4, G4, C5):              # l'arpege qui monte
        note(0, idx, 8)
    s += bytes((0x90, 6))
    for a, b, c in ((C3, E4, G4), (G3, E4, C5)):          # deux accords
        s.extend((0x80, a, 0x81, b, 0x82, c, 40))
    s += bytes((0x90, 0x91, 0x92, 25, 0xE0))
    return bytes((0x4D, 0x42, 0x31, 0x00)) + len(s).to_bytes(2, 'little') + b'\x08\x00' + s


# ── L'Applesoft ────────────────────────────────────────────────────────────
def applesoft(lines):
    out, addr = bytearray(), 0x0801
    for num, toks in lines:
        body = num.to_bytes(2, 'little') + toks + b'\x00'
        addr += 2 + len(body)
        out += addr.to_bytes(2, 'little') + body
    return bytes(out) + b'\x00\x00'


HOME, PRINT, FOR, TO, NEXT, END = 0x97, 0xBA, 0x81, 0xC1, 0x82, 0x80

SAMPLE = """\
A2 FILE CMD -- SAMPLE TEXT

This file is here so you can try the viewers and the editor.

  T   read it page by page
  H   the same bytes in hexadecimal
  E   edit it: type, ESC for the menu, S to save

The two images in this folder are test cards, not photographs:
DHGR.RLE shows the sixteen double hi-res colours as vertical
bars, HGR.RLE the six colours of plain hi-res as horizontal
bands. Press I on either one, then LEFT and RIGHT to leaf
through the folder as if it were an album.

WELCOME.MB is a short three-voice fanfare for a Mockingboard.
Press RETURN on it; P pauses and resumes.

Nothing on this disk is copied from anywhere: the cards, the
tune and this text are all generated by tools/mkdemo.py.
"""


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'DHGR.RLE.BIN').write_bytes(image(b'DHRR', 16384, dhgr_card()))
    (out / 'HGR.RLE.BIN').write_bytes(image(b'HGRR', 8192, hgr_card()))
    (out / 'WELCOME.MB.BIN').write_bytes(fanfare())
    (out / 'SAMPLE.TXT').write_bytes(SAMPLE.replace('\n', '\r').encode('ascii'))
    (out / 'HELLO#FC0801').write_bytes(applesoft([
        (10, bytes([HOME])),
        (20, bytes([PRINT]) + b'"A2 FILE CMD RUNS APPLESOFT."'),
        (30, bytes([PRINT])),
        (40, bytes([PRINT]) + b'"TYPE  -A2FILE.SYSTEM  TO COME BACK."'),
        (50, bytes([END])),
    ]))
    for f in sorted(out.iterdir()):
        print(f'  {f.name:<16} {f.stat().st_size:>6} octets')
    return 0


if __name__ == '__main__':
    sys.exit(main())
