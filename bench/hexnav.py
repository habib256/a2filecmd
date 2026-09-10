#!/usr/bin/env python3
"""HEX direct navigation: 24-bit offsets, first/last, bounds and empty files."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all, RET, ESC

DATA = bytes((i * 7 + i // 256) & 255 for i in range(100001))
FILES = {'WORK/LARGE.BIN': DATA, 'WORK/EMPTY.TXT': b''}


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-hexnav-') as tmp:
        with boot_hd(Path(tmp), FILES, port=6816) as (p, s):
            s.select('WORK'); s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()
            stack = p.peek(0x80, 2)
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5' * 8)

            def page(offset):
                base = offset // 320 * 320
                s.wait(lambda: s.rows()[0].startswith('%05X ' % base), 'page %X' % base, 30)
                p.stable()
                want = '%05X ' % base + ''.join('%02X ' % v for v in DATA[base:base + 16])
                s.ok('page %05X : adresse et octets exacts' % base, s.rows()[0].startswith(want), s.rows()[0])

            def go(value, end=RET):
                s.key(b'G'); s.wait(lambda: s.has('Offset:'), 'offset prompt')
                if value: s.type(value)
                s.key(end)

            s.select('LARGE'); s.key(b'H'); page(0)
            go('010023'); page(0x10023)
            s.key(b' '); page(0x10023 // 320 * 320 + 320)
            s.key(b'B'); page(0x10023)
            go('000100', ESC); page(0x10023)
            go('FFFFFE'); s.wait(lambda: s.has('Past EOF'), 'past EOF')
            s.ok('adresse hors fichier signalee', s.has('Past EOF'))
            s.key(RET); page(0x10023)
            go('%06X' % len(DATA)); s.wait(lambda: s.has('Past EOF'), 'exact EOF'); s.key(RET); page(0x10023)
            s.key(b'e'); page(len(DATA) - 1)
            s.key(b' '); page(len(DATA) - 1)
            s.ok('derniere page : dernier octet et remplissage',
                 s.rows()[10].startswith('%05X %02X ' % (100000, DATA[-1])) and not s.rows()[11].strip())
            s.key(b'r'); page(0)
            s.key(b'B'); page(0)
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'panels'); p.stable()
            s.ok('selection conservee', s.line(0).startswith('LARGE '))
            s.select('EMPTY'); s.key(b'H'); s.wait(lambda: s.has('page 1/1'), 'empty'); p.stable()
            s.key(b'E'); s.key(b'R'); go('000000')
            s.wait(lambda: s.has('page 1/1'), 'empty zero'); p.stable()
            s.ok('fichier vide : navigation bornee', all(not r.strip() for r in s.rows()[:20]))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'final panels'); p.stable()
            s.ok('pile restauree et bornee', p.peek(0x80, 2) == stack and p.peek(floor, 8) == b'\xa5' * 8)
    return ok_all(s, 'hexnav')


if __name__ == '__main__':
    sys.exit(main())
