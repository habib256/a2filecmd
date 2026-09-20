#!/usr/bin/env python3
"""Cycle cost of Mini's catalog and copy paths, on disposable images only.

Reports the totals and, for the copy's writing phase, the per-RWTS-call
detail: calls by command and by drive, cycles spent inside RWTS against
cycles spent between calls, and the revolutions each data sector costs.

Usage: python3 bench/mini33_time.py --pom2-root /path/to/pom2
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk
from mkmini33 import MINI_VERSION
from mini33_fixture import read_files as _read_files

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT/f'dist/A2FILECMD-DOS3.3-{MINI_VERSION}.dsk')
p.add_argument('--max-rev-per-sector', type=float, default=None,
               help='fail when a data sector costs more disk revolutions than this '
                    '(off by default: the current build is known slow)')
a = p.parse_args()

original = a.disk.read_bytes()
MINI_ENV = dict(os.environ, MINI_FILES=str(len(_read_files(original))))   # the boot disk's file count, for the screen checks
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
    # Streamed and kept: the run takes minutes, and the revolution figure is
    # read back from the output below.
    proc = subprocess.Popen([str(d / 'bench'), str(a.pom2_root), str(boot), str(target)], env=MINI_ENV,
                            stdout=subprocess.PIPE, text=True)
    out = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        out.append(line)
    if proc.wait(timeout=1800) != 0:
        sys.exit(f'bench exited with {proc.returncode}')
    assert boot.read_bytes() == original, 'boot image changed'
    assert a.disk.read_bytes() == original, 'source image changed'

if a.max_rev_per_sector is not None:
    m = re.search(r'([\d.]+) revolutions per sector', ''.join(out))
    assert m, 'no revolutions-per-sector line in the bench output'
    rev = float(m.group(1))
    if rev > a.max_rev_per_sector:
        sys.exit(f'FAIL: {rev:.2f} revolutions per data sector, '
                 f'limit {a.max_rev_per_sector:.2f}')
    print(f'PASS: {rev:.2f} revolutions per data sector, '
          f'limit {a.max_rev_per_sector:.2f}')
