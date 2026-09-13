#!/usr/bin/env python3
"""Cycle cost of Mini's catalog and copy paths, on disposable images only.

Usage: python3 bench/mini33_time.py --pom2-root /path/to/pom2
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT / 'dist/A2FC-MINI-DOS33-0.6.0.dsk')
a = p.parse_args()

original = a.disk.read_bytes()
with tempfile.TemporaryDirectory(prefix='mini33-time-') as tmp:
    d = Path(tmp)
    boot, target = d / 'boot.dsk', d / 'target.dsk'
    boot.write_bytes(original)
    target.write_bytes(make_disk([('KEEP.DST', 0x80, b'PRESERVE THESE BYTES\r\0')]))
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_time.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(target)],
                   check=True, timeout=1800)
    assert boot.read_bytes() == original, 'boot image changed'
    assert a.disk.read_bytes() == original, 'source image changed'
