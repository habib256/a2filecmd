#!/usr/bin/env python3
"""RETURN opens a file by its content; RETURN and B run a DOS binary.

RETURN reads the first data sector: a raw or BSAVEd picture opens as
hi-res, a binary holding text in the text viewer, a binary that cannot
run and a T file that is not text in hex, and a 33-sector program at
$0800 asks BRUN. The program is BRUN from drive 2, once with A2FC Mini
started by HELLO and once from the DOS prompt, and proves each run by
counting in $06 (and writing $5A to $07). Temporary images only."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk
from mkmini33 import MINI_VERSION
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT/f'dist/A2FC-MINI-DOS33-{MINI_VERSION}.dsk')
a = p.parse_args()
original = a.disk.read_bytes()
picture = bytes((0x55, 0x2A) * 4096)
# INC $06 / LDA #$5A / STA $07 / RTS, loaded at $6000 (over A2FC Mini)
game = bytes((0x00, 0x60, 7, 0)) + bytes((0xE6, 0x06, 0xA9, 0x5A, 0x85, 0x07, 0x60))
with tempfile.TemporaryDirectory(prefix='mini33-brun-') as tmp:
    d = Path(tmp)
    boot, other = d / 'boot.dsk', d / 'other.dsk'
    boot.write_bytes(original)
    def bsave(address, body):
        return bytes((address & 255, address >> 8, len(body) & 255, len(body) >> 8)) + body
    note = b'THIS BINARY HOLDS TEXT\rSECOND LINE\r'
    other_image = make_disk([
        ('PIC', 4, picture), ('GAME', 4, game),
        ('PIC2', 4, bsave(0x2000, bytes((0x11, 0x22) * 4096))),
        ('NOTE.BIN', 4, bsave(0x4000, note)),
        ('ROMPATCH', 4, bsave(0xC000, bytes(range(8)))),
        ('PAGE3', 4, bsave(0x0300, bytes(range(8)))),
        ('BIGGAME', 4, bsave(0x0800, bytes((0xA9, 0x00, 0x85, 0x06, 0x60)) * 1637 + bytes(3))),
        ('JUNK', 0, bytes(range(1, 32)) * 8)])
    other.write_bytes(other_image)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_brun.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(other)],
                   check=True, timeout=300)
    assert other.read_bytes() == other_image, 'the program disk was written'
    assert a.disk.read_bytes() == original
    print('PASS: RETURN picks hi-res, text, hex or BRUN by content; RETURN and B BRUN a binary from HELLO and from the DOS prompt')
