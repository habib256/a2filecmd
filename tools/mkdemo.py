#!/usr/bin/env python3
"""Fabrique les fichiers de demonstration de la disquette A2 File Cmd.

    mkdemo.py DOSSIER [--small]

Rien n'est emprunte : tout est calcule ici, et donc redistribuable sans
question. La disquette a besoin de quoi essayer chaque visionneuse, et une
mire vaut mieux qu'une photo pour cela -- on voit tout de suite si le
decodage des couleurs est juste.

  DHGR.RLE   les seize couleurs du double haute resolution, en barres,
             compressees dans le flux DHRR v1 que lit A2 File Cmd
  DHGR.RAW   la meme mire, page brute de 16 384 octets
  HGR.RLE    les six couleurs du haute resolution simple, flux HGRR v1
  HGR.RAW    la meme mire, page brute de 8 192 octets
  WELCOME.MB une fanfare de trois voix pour la Mockingboard, flux MB1
  SAMPLE.TXT un texte pour la visionneuse et l'editeur
  HELLO      un programme Applesoft, si BASIC.SYSTEM est sur le volume
  SAMPLE.SHK le texte et le programme dans une archive ShrinkIt (LZW/2)
  SAMPLE.BNY les memes dans une archive Binary II
  TINY.PO    une petite image de disquette ProDOS (64 blocs, un dossier)
  TINY.2MG   la meme, habillee de l'en-tete 2IMG
  DOS33.DSK  une disquette DOS 3.3 : un texte, un Applesoft, un binaire
  LETTER     un document AppleWorks (traitement de texte), pour la surcouche AWP

Le tout tient sur le .2mg ; la disquette 5,25 n'a pas la place et ne porte
que le programme.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mkawp
import mkbny
import mkdos33
import mkshk
import po22mg

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
    """16 384 octets, plan AUX puis plan MAIN : les seize couleurs DHGR en
    bandes horizontales (une couleur par bande), un cadre blanc.

    Une couleur DHGR est un quartet repete en un flux CONTINU de bits, que les
    octets de 7 bits decoupent sans egard pour lui : la meme couleur donne
    quatre octets differents par periode de 28 bits, deux par plan. Un seul
    octet repete ne fait une couleur unie que pour 0, 5, 10 et 15 -- la
    version "un octet par bande" de la 0.6.6 et de la 0.6.7 rayait les douze
    autres (bench/run.py regarde maintenant le rendu, pas la memoire seule).
    Douze kilo-octets en RLE : c'est le .2mg qui la porte, pas la disquette."""
    aux, main = bytearray(8192), bytearray(8192)
    for row in range(192):
        off = hgr_offset(row)
        band = 15 if row < 3 or row >= 189 else min((row - 3) * 16 // 186, 15)
        bits = []
        for x in range(140):
            nib = 15 if x < 2 or x >= 138 else band     # cadre blanc a gauche/droite
            bits += [(nib >> b) & 1 for b in range(4)]
        for j in range(80):
            byte = sum(bits[j * 7 + k] << k for k in range(7))
            (aux if j % 2 == 0 else main)[off + j // 2] = byte
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


LETTER = """\
*A2 FILE CMD* -- A LETTER FROM APPLEWORKS

Dear reader,

This document was written for the AppleWorks word processor, the program that
most Apple II owners used to type their letters, their reports and their
newsletters. It is a type $1A file: three hundred bytes of header, then one
record per line, with the carriage return flagged on the last line of each
paragraph and the formatting -- *bold*, underline, centering -- kept as small
codes between the characters.

A2 File Cmd shows it as plain text: press RETURN or T on the file and read it
page by page, SPACE for the next page, B for the previous one, ESC to come back.
The formatting codes are skipped, tabulations are rendered:

\tName\tType\tSize
\tLETTER\tAWP\ta few blocks

The file itself was generated by tools/mkawp.py, which knows the format well
enough to write it and to read it back, so that the bench can compare what the
Apple IIe shows with what was written.

Yours faithfully,

The maker of demos
"""


def make(out, full=True):
    """Ecrit les fichiers dans `out` ; `full` ajoute ce qui ne tient que sur le .2mg."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'DHGR.RLE.BIN').write_bytes(image(b'DHRR', 16384, dhgr_card()))
    (out / 'HGR.RLE.BIN').write_bytes(image(b'HGRR', 8192, hgr_card()))
    (out / 'WELCOME.MB.BIN').write_bytes(fanfare())
    (out / 'SAMPLE.TXT').write_bytes(SAMPLE.replace('\n', '\r').encode('ascii'))
    mkawp.write_awp(out / 'LETTER#1A0000', LETTER)
    hello = applesoft([
        (10, bytes([HOME])),
        (20, bytes([PRINT]) + b'"A2 FILE CMD RUNS APPLESOFT."'),
        (30, bytes([PRINT])),
        (40, bytes([PRINT]) + b'"TYPE  -A2FILE.SYSTEM  TO COME BACK."'),
        (50, bytes([END])),
    ])
    (out / 'HELLO#FC0801').write_bytes(hello)
    if full:
        sample = SAMPLE.replace('\n', '\r').encode('ascii')
        (out / 'DHGR.RAW.BIN').write_bytes(dhgr_card())
        (out / 'HGR.RAW.BIN').write_bytes(hgr_card())
        inside = [{'name': 'SAMPLE', 'data': sample, 'filetype': 0x04},
                  {'name': 'HELLO', 'data': hello, 'filetype': 0xFC, 'auxtype': 0x0801}]
        mkshk.write_shk(out / 'SAMPLE.SHK', inside)
        mkbny.write_bny(out / 'SAMPLE.BNY', inside)
        with tempfile.TemporaryDirectory() as tmp:
            tiny = Path(tmp) / 'tiny'
            (tiny / 'INSIDE').mkdir(parents=True)
            (tiny / 'INSIDE/DEEP.TXT').write_bytes(b'deep inside the image\r')
            (tiny / 'HELLO.TXT').write_bytes(b'hello from inside a disk image\r' * 20)
            subprocess.run([sys.executable, str(Path(__file__).with_name('mkvolume.py')), str(tiny),
                            str(out / 'TINY.PO'), '--volume', 'TINY', '--blocks', '64'],
                           check=True, capture_output=True)
        (out / 'TINY.2MG').write_bytes(po22mg.to_2mg((out / 'TINY.PO').read_bytes()))
        (out / 'DOS33.DSK').write_bytes(mkdos33.build([
            ('GREETINGS', 0x00, b'HELLO FROM A DOS 3.3 DISK\r' * 4 + b'\x00'),
            ('MYPROG', 0x02, bytes([0x05, 0x00]) + b'\x00\x00'),
            ('BINFILE', 0x04, bytes([0x00, 0x20, 0x04, 0x00]) + b'\x01\x02\x03\x04'),
        ]))
    return out


def main():
    out = make(sys.argv[1], full='--small' not in sys.argv[2:])
    for f in sorted(out.iterdir()):
        print(f'  {f.name:<16} {f.stat().st_size:>6} octets')
    return 0


if __name__ == '__main__':
    sys.exit(main())
