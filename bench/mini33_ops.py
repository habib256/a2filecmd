#!/usr/bin/env python3
"""HGR, exclusive TXT create, and delete, on temporary images only."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from mini33_fixture import make_disk, read_files
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--pom2-root', type=Path, required=True)
p.add_argument('--disk', type=Path, default=ROOT / 'dist/A2FC-MINI-DOS33-0.7.0.dsk')
a = p.parse_args()
original = a.disk.read_bytes()
picture = bytes((0x55, 0x2A) * 4096)
with tempfile.TemporaryDirectory(prefix='mini33-ops-') as tmp:
    d = Path(tmp)
    boot = d / 'boot.dsk'
    other = d / 'other.dsk'
    boot.write_bytes(original)
    other_image = make_disk([('PIC', 4, picture), ('KEEP.DST', 0, b'SAFE')])
    other.write_bytes(other_image)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_ops.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(other)],
                   check=True, timeout=180)
    after_boot = read_files(boot.read_bytes())
    after_other = read_files(other.read_bytes())
    assert 'NOTE' not in after_boot
    assert 'MEMO' not in after_boot
    assert after_other['PIC']['data'] == picture
    assert after_other['KEEP.DST']['data'].rstrip(b'\x00') == b'SAFE'
    boot_files = read_files(original)
    assert after_other['HELLO']['data'] == boot_files['HELLO']['data']
    assert after_other['README']['data'] == boot_files['README']['data']
    assert 'A2FC.MINI' not in after_other
    assert a.disk.read_bytes() == original
    print('PASS: picture untouched; NOTE created then deleted; tagged HELLO+README copied; master unchanged')
