#!/usr/bin/env python3
"""Review fixes through the real UI, on temporary images; checks file bytes."""
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
a = p.parse_args()


def high(text):
    return bytes(c | 0x80 for c in text)


original = a.disk.read_bytes()
MINI_ENV = dict(os.environ, MINI_FILES=str(len(read_files(original))))   # the boot disk's file count, for the screen checks
copy_fixture = bytearray(make_disk([('GOOD.A', 0, b'GOOD DATA A'),
                                    ('BAD.B', 0, b'BAD DATA B')]))
copy_fixture[offset(17, 15) + 11 + 35 + 33] = 9     # a count the chain does not have
copy_fixture = bytes(copy_fixture)
edit_fixture = make_disk([('TEXT.DOS', 0, high(b'ONE\rTWO\r')),
                          ('FULL.TXT', 0, bytes([0xC1]) * 8192),
                          ('SAME.NAME', 0, b'SAME'),
                          ('DEL.1', 0, b'D1'), ('DEL.2', 0, b'D2'),
                          ('LOCKED.3', 0x80, b'L3'), ('KEEP.4', 0x80, b'K4')])
failures = []
with tempfile.TemporaryDirectory(prefix='mini33-review-') as tmp:
    d = Path(tmp)
    boot, first, second = d / 'boot.dsk', d / 'copy.dsk', d / 'edit.dsk'
    boot.write_bytes(original)
    first.write_bytes(copy_fixture)
    second.write_bytes(edit_fixture)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O2',
                    *['-I' + str(a.pom2_root / s) for s in ('src', 'include', 'build/generated')],
                    str(ROOT / 'bench/mini33_review.cpp'),
                    str(a.pom2_root / 'build/libpom2_core_test.a'),
                    '-o', str(d / 'bench')], check=True)
    ui = subprocess.run([str(d / 'bench'), str(a.pom2_root), str(boot), str(first), str(second)],
                        env=MINI_ENV, timeout=600)
    if ui.returncode:
        failures.append(f'{ui.returncode} screen checks')

    def expect(ok, what):
        print(('ok   ' if ok else 'FAIL ') + what)
        if not ok:
            failures.append(what)

    expect(first.read_bytes() == copy_fixture, 'the copy source is untouched')
    before, after = read_files(original), read_files(boot.read_bytes())
    for name, f in before.items():
        expect(after.get(name, {}).get('data') == f['data'], f'boot {name} preserved')
    expect(after.get('GOOD.A', {}).get('data', b'').rstrip(b'\0') == b'GOOD DATA A',
           'GOOD.A copied byte for byte')
    expect('BAD.B' not in after, 'BAD.B not published')
    was, now = read_files(edit_fixture), read_files(second.read_bytes())
    for name in ('TEXT.DOS', 'FULL.TXT', 'SAME.NAME'):
        expect(now.get(name, {}).get('entry') == was[name]['entry'] and
               now[name]['data'] == was[name]['data'], f'{name} entry and bytes unchanged')
    expect(now.get('EDITED', {}).get('data', b'').rstrip(b'\0') == high(b'ONE\rX\rTWO\r'),
           'F4: typed text and RETURN follow the file ($D8, $8D)')
    expect('DEL.1' not in now and 'DEL.2' not in now, 'F6: DEL.1 and DEL.2 deleted')
    expect(now.get('LOCKED.3', {}).get('type') == 0 and now['LOCKED.3']['data'] == was['LOCKED.3']['data'],
           'F6: LOCKED.3 unlocked, bytes kept')
    expect(now.get('KEEP.4', {}).get('type') == 0x80 and now['KEEP.4']['data'] == was['KEEP.4']['data'],
           'F6: KEEP.4 still locked, not deleted')
    expect(a.disk.read_bytes() == original, 'the --disk image is unchanged')
if failures:
    print('FAIL:', '; '.join(failures))
    sys.exit(1)
print('PASS: dest reread, marks kept, batch summaries, same-name rename, full text refused, $8D editing')
