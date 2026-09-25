#!/usr/bin/env python3
"""The heartbeat rwts.s lends to two of RWTS's JSRs changes nothing but
the screen: on temporary images only, the same session -- a never
formatted diskette read, formatted, then filled with every file of the
boot disk -- runs once with the JSRs lent and once with the lending
refused (the signature spoiled in memory, as another DOS would). Every
RWTS call must return the same carry, code and bytes, the two diskettes
must come out byte for byte identical, a WRITE never runs with a site
lent, and after Q DOS catalogs both disks with the resident gone."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import read_files
from mkmini33 import MINI_VERSION
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT/f'dist/A2FILECMD-DOS3.3-{MINI_VERSION}.dsk')
a = p.parse_args()
original = a.disk.read_bytes()
MINI_ENV = dict(os.environ, MINI_FILES=str(len(read_files(original))))

with tempfile.TemporaryDirectory(prefix='mini33-lend-') as tmp:
    d = Path(tmp)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_lend.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    logs, disks = {}, {}
    for mode in ('lend', 'plain'):
        boot = d / f'boot-{mode}.dsk'
        fresh = d / f'fresh-{mode}.dsk'
        boot.write_bytes(original)
        fresh.write_bytes(bytes(143360))
        r = subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(fresh), mode],
                           env=MINI_ENV, check=True, timeout=900,
                           stdout=subprocess.PIPE, text=True)
        logs[mode] = r.stdout.splitlines()
        assert boot.read_bytes() == original, 'the boot disk is read-only'
        disks[mode] = fresh.read_bytes()
    assert a.disk.read_bytes() == original
    lend, plain = logs['lend'], logs['plain']
    for i, (x, y) in enumerate(zip(lend, plain)):
        assert x == y, f'RWTS call {i}: lent {x!r}, plain {y!r}'
    assert len(lend) == len(plain), (len(lend), len(plain))
    failed = [l for l in lend if ' carry 1 ' in l]
    reads = [l for l in lend if l.startswith('1 ')]
    assert failed and any(l.startswith('1 ') for l in failed), 'no failed read was compared'
    assert disks['lend'] == disks['plain'], 'the two diskettes differ'
    files = read_files(disks['lend'])
    assert set(files) == set(read_files(original))
    print(f'PASS: {len(lend)} RWTS calls ({len(reads)} reads, {len(failed)} failed) '
          'identical with and without the lent JSRs, the two diskettes byte for byte '
          'identical, no WRITE with a site lent, DOS alone after Q')
