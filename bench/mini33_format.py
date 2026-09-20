#!/usr/bin/env python3
"""F, the format, on temporary images only: then the result boots. Once
on a disk holding files, once on a zero-filled image, once on a diskette
that was never formatted (no address fields), as a user would."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk, read_files, offset
from mkmini33 import MINI_VERSION
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT/f'dist/A2FILECMD-DOS3.3-{MINI_VERSION}.dsk')
p.add_argument('--no-fresh', action='store_true',
               help='skip the never formatted diskette (POM2 insertBlankDisk, its legacy nibble gate fixed 2026-09-16)')
a = p.parse_args()
original = a.disk.read_bytes()
before = read_files(original)
MINI_ENV = dict(os.environ, MINI_FILES=str(len(read_files(original))))   # the boot disk's file count, for the screen checks


def sector(disk, t, s):
    o = offset(t, s)
    return disk[o:o + 256]


with tempfile.TemporaryDirectory(prefix='mini33-format-') as tmp:
    d = Path(tmp)
    boot = d / 'boot.dsk'
    other = d / 'other.dsk'
    boot.write_bytes(original)
    other.write_bytes(make_disk([('OLD', 0, b'GONE AFTER FORMAT'),
                                 ('KEEP', 4, bytes(range(256)) * 3)]))
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_format.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(other), 'format'],
                   env=MINI_ENV, check=True, timeout=900)
    assert boot.read_bytes() == original, 'the boot disk is read-only'
    assert a.disk.read_bytes() == original
    fresh = other.read_bytes()
    for t in range(3):
        for s in range(16):
            assert sector(fresh, t, s) == sector(original, t, s), (t, s)
    v = sector(fresh, 17, 0)
    assert v[1:4] == bytes([17, 15, 3]) and v[6] == 254 and v[0x27] == 122
    assert v[0x34:0x38] == bytes([35, 16, 0, 1])
    assert v[0x38:0x44] == bytes(12), 'DOS tracks stay reserved'
    assert v[0x38 + 17 * 4:0x3c + 17 * 4] == bytes(4)
    files = read_files(fresh)
    assert set(files) == set(before), (set(files), set(before))
    for name in files:
        assert files[name]['data'] == before[name]['data'], name
        assert files[name]['type'] == before[name]['type'], name
        for t, s in files[name]['blocks'] + files[name]['lists']:
            assert t >= 3 and t != 17
    # Bootable: drive 1 is now the disk made above.
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(other), str(boot), 'boot'],
                   env=MINI_ENV, check=True, timeout=300)
    # The same from a blank disk (all zero: no VTOC, no catalog), watching
    # the progress bar and the key bar while it formats.
    blank = d / 'blank.dsk'
    blank.write_bytes(bytes(143360))
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(blank), 'blank'],
                   env=MINI_ENV, check=True, timeout=900)
    assert boot.read_bytes() == original
    fresh = blank.read_bytes()
    for t in range(3):
        for s in range(16):
            assert sector(fresh, t, s) == sector(original, t, s), (t, s)
    files = read_files(fresh)
    assert set(files) == set(before), (set(files), set(before))
    for name in files:
        assert files[name]['data'] == before[name]['data'], name
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(blank), str(boot), 'boot'],
                   env=MINI_ENV, check=True, timeout=300)
    if a.no_fresh:
        print('PASS: format with DOS from the panels, files copied, the result boots; '
              'the same from a zero-filled image, with the progress bar; master unchanged')
        sys.exit(0)
    # A diskette that was never formatted: the surface has no address
    # fields until RWTS formats it; the file is where the result lands.
    fresh_disk = d / 'fresh.dsk'
    fresh_disk.write_bytes(bytes(143360))
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(fresh_disk), 'fresh'],
                   env=MINI_ENV, check=True, timeout=900)
    assert boot.read_bytes() == original
    fresh = fresh_disk.read_bytes()
    for t in range(3):
        for s in range(16):
            assert sector(fresh, t, s) == sector(original, t, s), (t, s)
    files = read_files(fresh)
    assert set(files) == set(before), (set(files), set(before))
    for name in files:
        assert files[name]['data'] == before[name]['data'], name
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(fresh_disk), str(boot), 'boot'],
                   env=MINI_ENV, check=True, timeout=300)
    print('PASS: format with DOS from the panels, files copied, the result boots; '
          'the same from a zero-filled image and from a never formatted diskette; '
          'master unchanged')
