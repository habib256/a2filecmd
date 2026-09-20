#!/usr/bin/env python3
"""Help layout, bundled recovery guide and recovery on a disposable volume."""
import os
import sys
from pathlib import Path
import tempfile
import urllib.request
from xplug import boot_hd, RET, ESC, TAB, ok_all
from pom2 import BUILD
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from prodos_read import Image


def files(image, key=2, prefix=''):
    result = {}
    for entry in image.entries(key):
        name = prefix+'/'+entry[1:1+(entry[0]&15)].decode()
        if entry[0] >> 4 == 13:
            result.update(files(image, int.from_bytes(entry[17:19], 'little'), name))
        else:
            result[name] = image.read(entry)
    return result


def main():
    old, new = b'OLD CONTENT: KEEP ME\r', b'NEW CONTENT: RECOVER ME\r'
    with tempfile.TemporaryDirectory(prefix='a2fc-recovery-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, {'BROKEN/A2FC.COPY#040000': new,
                           'BROKEN/A2FC.BAK#040000': old,
                           'SAFE/KEEP#040000': b'UNRELATED\r'}, port=6988) as (p, s):
            s.key(b'?'); s.wait(lambda: s.has('Back to panels'), 'help'); p.stable()
            rows = s.rows()
            s.ok('help points to RECOVER', 'RECOVER' in rows[2])
            s.ok('last help row fits and leaves the footer clean',
                 rows[22].strip() == 'RET Open       T  Text       H  Hex       L/R Prev/next       ESC Back/menu'
                 and rows[23].strip() == 'ANY Back to panels', repr(rows[22:24]))
            output = Path(os.environ.get('A2FC_RECOVERY_CAPTURES', '/tmp/a2fc-recovery-captures'))
            output.mkdir(parents=True, exist_ok=True)
            (output/(BUILD.name+'.ppm')).write_bytes(urllib.request.urlopen(p.base+'/screen.ppm').read())
            (output/(BUILD.name+'.txt')).write_text('\n'.join(rows)+'\n')
            s.key(ESC); p.stable()
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('RECOVER'); s.key(RET)
            s.wait(lambda: s.has('KEEP THE EVIDENCE'), 'recovery guide')
            s.ok('bundled guide opens in the text viewer', s.has('RECOVERY AFTER'))
            s.key(ESC); p.stable()
            s.key(TAB); s.key(b'/'); s.select('/WORKHD', x=40); s.key(RET)
            s.select('SAFE', x=40); s.key(RET); p.stable(); s.key(TAB)
            s.select('BROKEN'); s.key(RET); p.stable(); s.select('A2FC.COPY')
            s.key(b'C'); s.wait(lambda: s.has('Failed; source kept.'), 'reserved recovery name refused')
            s.ok('reserved name is refused before recovery', True)
            s.key(b'R'); s.wait(lambda: s.has('New name'), 'rename on working duplicate')
            # Rename prompts start with the old name. Clear it first.
            s.key(b'\x08'*15); s.type('RECOV.NEW'); s.key(RET); p.stable()
            s.select('RECOV.NEW'); s.key(b'C')
            s.wait(lambda: s.has('copied'), 'verified recovered copy', 60); p.stable()
            s.ok('recovered candidate copied and verified', s.has('copied'))
            disk = Path(p.hdv)
        got = files(Image(disk.read_bytes()))
        s.ok('old backup and renamed candidate preserved exactly',
             got['/BROKEN/A2FC.BAK'] == old and got['/BROKEN/RECOV.NEW'] == new)
        s.ok('recovered bytes and unrelated destination preserved',
             got['/SAFE/RECOV.NEW'] == new and got['/SAFE/KEEP'] == b'UNRELATED\r')
        return ok_all(s, 'recovery')


if __name__ == '__main__':
    raise SystemExit(main())
