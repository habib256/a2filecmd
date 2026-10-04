#!/usr/bin/env python3
"""Graphics Magician pictures (GMAGIC, src/plugins/gmagic.s), end to end on
POM2: Return on a picture file draws it, page 1 read back byte for byte
against tools/gmagic_ref.py (written from docs/GRAPHICS-MAGICIAN-FORMAT.md).

    make disk && python3 bench/gmagic.py                       # 6502 build
    A2FC_BUILD=build python3 bench/gmagic.py                   # 65C02 build

The files are synthetic (tools/mkdemo_viewers.py's DEMO group, Appendix B's
room with its overlay, a 1984 picture with text): no Penguin picture. What
is checked: V82 by default, D redraws in V84; N steps through a group (and
back to the first), O draws a room's overlay over it; a picture with text is
V84 (A2FC's font), D changes nothing; Right goes to the next picture of the
folder, past a program, and round; S brings the next one by itself; Escape
gives the panels back; the auxiliary bank (/RAM) is untouched; a program
BIN opens in hex, a picture damaged past its first bytes is refused with
GMAGIC's message; on disk, every file is unchanged (read-only).
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET, ESC
from prodos_read import Image
import gmagic_ref as ref
import mkdemo_viewers

PORT = 6867
RIGHT = b'\x15'


def text_picture():
    P = ref.P
    b = bytearray(b'\x24\x60\x46')                     # blue
    b += P(0x80, 0, 0) + P(0xA0, 279, 0) + P(0xA0, 279, 191) + P(0xA0, 0, 191) + P(0xA0, 0, 0)
    b += P(0xE0, 140, 96) + b'\x60\x34'                # white letters
    b += P(0x10, 60, 80)
    for ch in b'GRAPHICS MAGICIAN':
        b += bytes([0x50, ch])
    b += P(0x10, 76, 100)
    for ch in b'Penguin, 1984':
        b += bytes([0x50, ch])
    b += P(0x10, 92, 120)
    for ch in b'A2FC font':
        b += bytes([0x30, ch])                         # XOR
    return bytes(b + b'\x00')


def settled(p, want, what, s, seconds=120):
    """The page equals want and stays so (the drawing is progressive)."""
    s.wait(lambda: bytes(p.peek(0x2000, 8192)) == want, what, seconds)
    time.sleep(0.5)
    return bytes(p.peek(0x2000, 8192)) == want


def main():
    group = mkdemo_viewers.gmagic()
    room = ref.corpus()['O01-picture-plus-overlay']
    text = text_picture()
    bad = ref.hand_made()['H02-colour-at-line-start'][:-1] + b'\x28\x00'   # colour 8 at the end
    prog = bytes.fromhex('4C0040A9008D00C0') + bytes(56)
    files = {'WORK/GM.GROUP#064000': group, 'WORK/PROGRAM#064000': prog,
             'WORK/ROOM#066800': room, 'WORK/TITLE#064000': text,
             'OTHER/DAMAGED#064000': bad}
    assert ref.dialect_of(text) == ref.V84 and ref.dialect_of(group) == ref.V82
    with tempfile.TemporaryDirectory(prefix='a2fc-gmagic-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT) as (p, s):
            def panels(what):
                s.wait(lambda: s.has('Type  Aux'), 'the panels after ' + what, 60)
                p.stable()

            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            s.select('GM.GROUP')
            aux = bytes(p.peek(0x0800, 0xB700, 'aux'))
            s.key(RET)
            v = lambda d, b, l, data=group: ref.view(data, d, b, l)
            s.ok('Return draws the first picture of the group, V82', settled(p, v(ref.V82, 0, 0), 'picture 0', s))
            blocks = ref.text_blocks()
            text_page = bytes(p.peek(0x0400, 0x400))
            s.ok('the font and the row patterns in the text page blocks',
                 all(text_page[i * 128:i * 128 + 112] == blocks[i] for i in range(8)))
            s.key(b'N')
            s.ok('N: the second picture (the palette)', settled(p, v(ref.V82, 1, 1), 'picture 1', s))
            s.key(b'N')
            s.ok('N: the third picture (the brushes)', settled(p, v(ref.V82, 2, 2), 'picture 2', s))
            s.key(b'D')
            s.ok('D: redrawn as V84', settled(p, v(ref.V84, 2, 2), 'V84', s))
            s.key(b'N')
            s.ok('N after the last: the first again', settled(p, v(ref.V84, 0, 0), 'picture 0 again', s))

            s.key(RIGHT)
            s.ok('Right: the room, past the program (V82 again)',
                 settled(p, v(ref.V82, 0, 0, room), 'the room', s))
            s.key(b'O')
            s.ok('O: its overlay drawn over it', settled(p, v(ref.V82, 0, 1, room), 'the overlay', s))
            s.key(RIGHT)
            want = ref.render(text, ref.V84)
            s.ok('Right: the picture with text, V84, A2FC font', settled(p, want, 'the title', s))
            s.key(b'D')
            time.sleep(2)
            s.ok('D changes nothing on a V84 picture', bytes(p.peek(0x2000, 8192)) == want)
            s.key(RIGHT)
            s.ok('Right on the last: round to the first', settled(p, v(ref.V82, 0, 0), 'round', s))
            s.key(b'S')
            s.ok('S: the slideshow brings the next picture by itself',
                 settled(p, v(ref.V82, 0, 0, room), 'the slideshow', s, 120))
            s.key(ESC); panels('the slideshow')
            s.ok('AUX and /RAM untouched', bytes(p.peek(0x0800, 0xB700, 'aux')) == aux)

            s.select('PROGRAM'); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 3, 'the program in hex', 30)
            s.ok('a program BIN opens in hex', True)
            s.key(ESC); panels('hex')

            s.key(b'<'); s.select('..'); s.key(RET); p.stable()
            s.select('OTHER'); s.key(RET); p.stable()
            s.select('DAMAGED'); s.key(RET)
            s.wait(lambda: s.has('Not a whole Graphics Magician picture'), 'the refusal', 60)
            s.ok('a damaged picture is refused with its message', True)
            hdv = Path(p.hdv)
        img = Image(hdv.read_bytes())
        for path, data in files.items():
            folder, name = path.split('#')[0].split('/')
            e = next(e for e in img.entries(dir_key(img, folder)) if e[1:1 + (e[0] & 15)].decode() == name)
            s.ok('on disk: %s unchanged' % name, img.read(e) == data)
    return ok_all(s, 'gmagic')


def dir_key(img, name):
    for e in img.entries(2):
        if e[1:1 + (e[0] & 15)].decode() == name:
            return int.from_bytes(e[0x11:0x13], 'little')
    raise KeyError(name)


if __name__ == '__main__':
    sys.exit(main())
