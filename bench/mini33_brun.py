#!/usr/bin/env python3
"""RETURN and B run a DOS binary from the panels; a picture still opens as hi-res.

The program is BRUN from drive 2, once with A2FC Mini started by HELLO and
once from the DOS prompt, and proves each run by counting in $06 (and
writing $5A to $07). Temporary images only."""
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
    other_image = make_disk([('PIC', 4, picture), ('GAME', 4, game)])
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
    print('PASS: RETURN on a picture shows it; RETURN and B BRUN a binary from HELLO and from the DOS prompt')
