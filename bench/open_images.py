#!/usr/bin/env python3
"""Return/I dispatch real pictures to their decoders; verify native screen bytes."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, RET, ESC, ok_all
from test_extasie import BASTILLE, unrle, page_of, COLS, ROWS
from test_paint816 import LADDER_PACKED, ladder_stream, page_left_to_right


def visible(page):
    return b''.join(page[i:i + 120] for i in range(0, 8192, 128))


def main():
    stream = unrle(BASTILLE)
    ext_aux, ext_main = page_of(stream[:COLS * ROWS]), page_of(stream[COLS * ROWS:])
    paint = page_left_to_right(ladder_stream())
    files = {
        'WORK/BASTILLE#F20000': BASTILLE,
        'WORK/PACKED#084000': bytes([255, 0x33]) * 32,
        'WORK/PAINT#06E001': LADDER_PACKED,
        'WORK/LORES#060400': bytes([0x55]) * 1024,
        'WORK/HEADER#040000': b'DGR\1\x28\x30\0\0' + bytes([0x66]) * 960,
        'WORK/STREAM#060000': b'HGRR\1\0\0\x20' + bytes([0xFF, 0x44]) * 63 + bytes([1, 0x44, 0x44]),
        'WORK/SPRITE#060000': bytes([0xF7]) * 48,
        'WORK/UNKNOWN#062000': bytes(range(100)),
        'WORK/ARAW#062000': bytes([0x11]) * 8192,
        'WORK/ZRAW#062000': bytes([0x22]) * 8192,
    }
    with tempfile.TemporaryDirectory(prefix='a2fc-open-images-') as tmp:
        with boot_hd(Path(tmp), files, port=6990,
                     plugins=['extasie', 'packfot', 'paint816', 'dgrview']) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET)
            s.select('WORK'); s.key(RET); p.stable()

            # No destructive AUX use before consent, including Return's new route.
            s.select('BASTILLE'); before = bytes(p.peek(0x1000, 0xB000, 'aux'))
            s.key(RET)
            s.wait(lambda: s.has('ALL /RAM files will be LOST'), 'Extasie consent', 30)
            s.ok('Return on Extasie asks before damaging RAM',
                 bytes(p.peek(0x1000, 0xB000, 'aux')) == before)
            s.key(b'N'); p.stable()
            s.ok('declining Extasie keeps RAM intact and avoids HEX',
                 bytes(p.peek(0x1000, 0xB000, 'aux')) == before and s.value('view', 1) == 0)

            for name, expected, aux in [('BASTILLE', ext_main, ext_aux),
                                        ('PACKED', bytes([0x33]) * 8192, None),
                                        ('PAINT', paint, None),
                                        ('STREAM', bytes([0x44]) * 8192, None)]:
                for key in (RET, b'I'):
                    label = name + (' Return' if key == RET else ' I')
                    s.select(name); s.key(key); s.allow_aux()
                    # One consent must be sufficient: a second prompt would time out.
                    s.wait(lambda: visible(bytes(p.peek(0x2000, 8192))) == visible(expected), label, 60)
                    s.ok(label + ' displays the decoded picture', True)
                    if aux is not None:
                        s.ok(label + ' decodes the auxiliary plane',
                             visible(bytes(p.peek(0x2000, 8192, 'aux'))) == visible(aux))
                    s.key(ESC)
                    s.wait(lambda: s.has('Type  Aux'), 'panels after ' + label, 30); p.stable()

            for name, color in [('LORES', 0x55), ('HEADER', 0x66)]:
                for key in (RET, b'I'):
                    s.select(name); s.key(key)
                    s.wait(lambda: bytes(p.peek(0x400, 40)) == bytes([color]) * 40, 'lo-res picture', 30)
                    s.ok(name + ' uses DGRVIEW ' + repr(key), True)
                    s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels after lo-res', 30); p.stable()

            s.select('SPRITE'); s.key(b'I')
            s.wait(lambda: s.has('Pixmap width'), 'sprite width', 30)
            s.key(b'01' + RET)
            s.wait(lambda: bytes(p.peek(0x413, 1)) == b'\x77', 'sprite pixels', 30)
            s.ok('I opens an unmarked sprite and asks only its width', True)
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels after sprite', 30); p.stable()

            s.select('UNKNOWN'); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 3, 'unknown binary HEX', 30)
            s.ok('ordinary BIN still opens in HEX', True)
            s.key(ESC); p.stable()
            s.select('BASTILLE'); s.key(b'H')
            s.wait(lambda: s.value('view', 1) == 3, 'explicit H on Extasie', 30)
            s.ok('H still explicitly opens Extasie in HEX', True)
            s.key(ESC); p.stable()

            # Specialized formats between ARAW and ZRAW must not enter raw's album.
            s.select('ARAW'); s.key(RET); s.allow_aux()
            s.wait(lambda: s.value('view', 1) == 1, 'raw image', 30)
            s.key(bytes([21]))
            s.wait(lambda: bytes(p.peek(0x2000, 8192)) == bytes([0x22]) * 8192, 'next raw image', 40)
            s.ok('raw album skips Extasie, PACKFOT, Paint and lo-res', True)
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'final panels', 30)
    return ok_all(s, 'open_images')


if __name__ == '__main__':
    sys.exit(main())
