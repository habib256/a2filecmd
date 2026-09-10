#!/usr/bin/env python3
"""Malformed GOTO configurations are refused before any action, with bytes preserved."""
import sys
import tempfile
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET

CASES = {
    'LONGPATH': b'/WORKHD/' + b'A' * 56 + b'\n',
    'NUL': b'/WORKHD\n\0/WORKHD/A2FILE\n',
    'TEN': b'/WORKHD\n' * 10,
    'OVERSIZE': b'\n' * 2001,
    'RELATIVE': b'WORKHD/DIR\n',
}
CHECK_BYTES = {'LONGPATH', 'NUL', 'TEN', 'OVERSIZE'}


def main():
    files = {'A2FILE/' + name + '#040000': data for name, data in CASES.items()}
    with tempfile.TemporaryDirectory(prefix='a2fc-gotobad-') as tmp:
        with boot_hd(Path(tmp), files, port=6818, plugins=['goto', 'crc']) as (p, s):
            s.select('A2FILE'); s.key(RET); s.wait(lambda: s.has('/WORKHD/A2FILE'), 'A2FILE'); p.stable()
            def rename(old, new):
                s.select(old); s.key(b'R'); s.wait(lambda: s.has('New name'), 'rename')
                s.key(b'\x7f' * len(old)); s.type(new); s.key(RET); p.stable(); s.select(new)

            for name, data in CASES.items():
                rename(name, 'GOTO.CFG')
                menu_run(s, p, 'GOTO')
                s.wait(lambda: s.has('Invalid GOTO.CFG'), 'invalid config'); p.stable()
                s.ok(name + ': refusal before showing favourites',
                     s.has('Type  Aux') and not s.has('GOTO -- favourite directories'))
                s.ok(name + ': active directory preserved', s.rows()[0].startswith('/WORKHD/A2FILE '))
                if name in CHECK_BYTES:
                    s.select('GOTO.CFG'); menu_run(s, p, 'CRC')
                    s.wait(lambda: s.has('CRC-32'), 'checksum'); p.stable()
                    expected = 'GOTO.CFG: CRC-32 $%08X, %d bytes' % (zlib.crc32(data), len(data))
                    s.ok(name + ': original bytes preserved', s.rows()[22].strip() == expected, s.rows()[22].strip())
                rename('GOTO.CFG', name)
    return ok_all(s, 'gotobad')


if __name__ == '__main__':
    sys.exit(main())
