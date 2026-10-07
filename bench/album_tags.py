#!/usr/bin/env python3
"""Tags across an album that leaves the first 139-entry window and comes back.

/WORKHD/BIG holds 150 entries (two windows); N100 and N131 are tagged in
the first. Bug hunt 2 (0.9.6, bench/probe_album_window_tags.py on the
reviewer's branch): N130.MB played, Right to N145.MB in the second window,
Left back to N130.MB, Escape -- the panel showed the names the tags were
set on, and the tags were gone: media_prepare and load_overlay saved them
again on the way to each neighbour, an empty set under the second window's
fingerprint. The control (an album inside the first window) kept them.

    A2FC_PORT_OFFSET=2000 python3 bench/album_tags.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all, RET, ESC  # noqa: E402

PORT = 6998
RIGHT = bytes([21])
LEFT = bytes([8])
MB = b'MB1\0\0\0\x08\0' + bytes([0xA0, 12, 0x80, 24]) + bytes([127]) * 30 + bytes([0xE0])


def name(i):
    return 'N%03d' % i + ('.MB' if i in (120, 130, 145) else '')


def main():
    files = {}
    for i in range(150):
        n = name(i)
        files['BIG/' + n + ('#061000' if n.endswith('.MB') else '#040000')] = MB if n.endswith('.MB') else b'x\r'
    with tempfile.TemporaryDirectory(prefix='a2fc-album-tags-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT, blocks=6000) as (p, s):
            panels = s.sym['_panels']

            def tags():
                t = p.peek(panels + 76, 18)
                return [i for i in range(144) if t[i >> 3] >> (i & 7) & 1]

            def first():
                return int.from_bytes(p.peek(panels + 68, 2), 'little')

            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('BIG'); s.key(RET); p.stable()
            for n in ('N100', 'N131'):
                s.select(n, tries=160); s.key(b' '); p.stable()
            want = tags()
            s.ok('two tags set in window 1', len(want) == 2, want)

            def album(start, there):
                s.select(start, tries=160); s.key(RET)
                s.wait(lambda: s.has('MB1 - ' + start), 'play ' + start, 60)
                s.key(RIGHT); s.wait(lambda: s.has('MB1 - ' + there), 'Right to ' + there, 120)
                s.key(LEFT); s.wait(lambda: s.has('MB1 - ' + start), 'Left back to ' + start, 120)
                s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels', 60); p.stable()

            album('N120.MB', 'N130.MB')
            s.ok('album inside window 1: tags kept', tags() == want, (tags(), first()))
            album('N130.MB', 'N145.MB')
            s.ok('album out to window 2 and back: tags kept', tags() == want,
                 (tags(), 'first=%u' % first()))
            s.ok('back on window 1', first() == 0, first())
    return ok_all(s, 'album_tags')


if __name__ == '__main__':
    raise SystemExit(main())
