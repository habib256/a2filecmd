#!/usr/bin/env python3
"""CRC-32 sous POM2, compare a zlib : limites de blocs et fichiers marques."""
import random
import sys
import tempfile
import zlib
from pathlib import Path

from xplug import boot_hd, menu_run, ok_all, RET, ESC


def main():
    rng = random.Random(6807)
    cases = {'EMPTY': b'', 'VECTOR': b'123456789'}
    for size in (1, 255, 256, 511, 512, 513, 2048):
        cases['B%d' % size] = rng.randbytes(size)
    with tempfile.TemporaryDirectory(prefix='a2fc-crc-') as tmp:
        files = {'WORK/' + name + '.BIN': data for name, data in cases.items()}
        with boot_hd(Path(tmp), files, port=6807, plugins=['crc']) as (p, s):
            s.select('WORK')
            menu_run(s, p, 'CRC')
            s.ok('un dossier est refuse', s.has('Select a file.'), s.rows()[22])
            s.key(RET)
            s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK')
            p.stable()
            stack = p.peek(0x80, 2)
            for name, data in cases.items():
                s.select(name)
                menu_run(s, p, 'CRC')
                expected = '%s: CRC-32 $%08X, %d bytes' % (name, zlib.crc32(data), len(data))
                s.wait(lambda: 'CRC-32' in s.rows()[22], name, 30)
                s.ok(name + ' identique a zlib', s.rows()[22].strip() == expected, s.rows()[22].strip())
            for name in ('VECTOR', 'B513'):
                s.select(name)
                s.key(b' ')
            menu_run(s, p, 'CRC')
            for name in ('VECTOR', 'B513'):
                expected = '%s: CRC-32 $%08X, %d bytes' % (name, zlib.crc32(cases[name]), len(cases[name]))
                s.ok(name + ' dans la liste marquee', s.has(expected), '\n'.join(s.rows()))
            s.key(ESC)
            p.stable()
            s.ok('retour aux panneaux', s.has('Type  Aux'))
            s.ok('pile C restauree', p.peek(0x80, 2) == stack)
    return ok_all(s, 'bench/crc.py')


if __name__ == '__main__':
    sys.exit(main())
