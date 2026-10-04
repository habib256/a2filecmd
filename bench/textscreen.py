#!/usr/bin/env python3
"""Text screen captures in DGRVIEW, on the emulated machine: what the screen
SHOWS, compared pixel for pixel with the character ROM.

A BIN at aux $0400 holding a text page (made here: a title screen in 40
columns, with inverse, flashing and MouseText bytes, and an 80-column one)
opens with Return in DGRVIEW, which recognises the text (looks_text) and
puts the Apple's own text mode on the air. /screen.ppm (280 x 192, 7 x 8
dots a cell in 40 columns) is compared with a rendering of the expected
page through POM2's character ROM -- the very glyphs the machine draws, the
flashing cells left out of the primary set's comparison (their phase is the
clock's). Then:
  - T shows the same bytes as lo-res (colours) and back; A switches to the
    alternate character set (MouseText);
  - nothing of AUX is written for 40 columns, and only the VISIBLE bytes of
    $0400-$07FF for 80; the screen holes of both banks are kept, though the
    file's own hole bytes are garbage;
  - a lo-res picture of the same metadata stays a picture, T reads it as
    text;
  - Escape gives back the panels exactly as they were drawn (the same
    picture: the character set the panels use is put back);
  - Right/Left between the captures never goes through the text screen of
    the panels (switch_to_text trapped, as bench/media.py does for lo-res).

    A2FC_IMG=A2FILECMD-full python3 bench/textscreen.py
    A2FC_BUILD=build-6502 A2FC_IMG=A2FILECMD-full A2FC_PRESET=iie_unenh python3 bench/textscreen.py
"""
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, RET, ESC, ok_all  # noqa: E402
from pom2 import PRESET, FULL  # noqa: E402
import textscreen_ref as ref  # noqa: E402

RIGHT, LEFT = b'\x15', b'\x08'
ROMS = Path(os.environ.get('POM2_ROOT', Path.home() / 'src/pom2')) / 'roms'
ROM = (ROMS / ('apple2e_char_2k.rom' if PRESET == 'iie_unenh' else 'apple2e_char_us.rom')).read_bytes()
VISIBLE = [o for o in range(1024) if o % 128 < 120]
HOLES = [o for o in range(1024) if o % 128 >= 120]


def text_page(lines, holes=0x5A):
    """A 40-column page of high-bit text; the hole bytes are garbage, as a
    BSAVE of a used screen leaves them."""
    p = bytearray(1024)
    for o in HOLES:
        p[o] = holes
    for r in range(24):
        line = lines[r] if r < len(lines) else ''
        at = ref.row_of(r)
        p[at:at + 40] = bytes(ord(c) | 0x80 for c in line.ljust(40)[:40])
    return p


def title():
    p = text_page(['', '   A2 FILE CMD SHOWS TEXT SCREENS', '', '   A PAGE SAVED FROM $0400 (BSAVE',
                   '   SCREEN,A$400,L$400) OPENS AS THE', '   APPLE II SHOWED IT, WITH lower case.',
                   '', '   T: LO-RES   A: CHARACTER SET'])
    at = ref.row_of(10) + 3                  # inverse, flashing / MouseText
    p[at:at + 7] = bytes(c & 0x3F for c in b'INVERSE')
    at = ref.row_of(12) + 3
    p[at:at + 5] = bytes(c & 0x3F | 0x40 for c in b'FLASH')
    return bytes(p)


def wide():
    """80 columns: the even columns in the first (auxiliary) half."""
    lines = ['', '  AN 80-COLUMN TEXT SCREEN: EVEN COLUMNS FROM AUX, ODD COLUMNS FROM MAIN.',
             '', '  The enhanced IIe shows it with the alternate character set.']
    aux, main = text_page([]), text_page([])
    for r, line in enumerate(lines):
        line = line.ljust(80)
        at = ref.row_of(r)
        aux[at:at + 40] = bytes(ord(c) | 0x80 for c in line[0::2])
        main[at:at + 40] = bytes(ord(c) | 0x80 for c in line[1::2])
    return bytes(aux + main), lines


def lores():
    p = bytearray(1024)
    for r in range(24):
        at = ref.row_of(r)
        c = (r // 3 + 1) & 15
        p[at:at + 40] = bytes([c * 17] * 40)
    return bytes(p)


def glyph_rows(b, alt):
    """POM2's ROM image: the first 256 glyphs are the alternate set (the
    MouseText at $40-$5F); the primary set differs from it only in the
    flashing $40-$7F, which render40 leaves out."""
    return [ROM[b * 8 + y] for y in range(8)]


def render(main, aux, alt, cols, skip_flash=False):
    """The picture POM2 shows for a text page: 280 x 192 in 40 columns,
    560 x 192 in 80 (even columns from AUX), 7 x 8 dots a cell, bit 0 the
    leftmost, a dot lit where the ROM's bit is clear. None where a
    flashing cell of the primary set makes the dots the clock's choice."""
    w = cols * 7
    out = [0] * (w * 192)
    for r in range(24):
        for c in range(cols):
            if cols == 40:
                b = main[ref.row_of(r) + c]
            else:
                b = (aux if c % 2 == 0 else main)[ref.row_of(r) + c // 2]
            flash = not alt and 0x40 <= b < 0x80
            g = glyph_rows(b, alt)
            for y in range(8):
                for x in range(7):
                    out[(r * 8 + y) * w + c * 7 + x] = None if (flash and skip_flash) else int(not (g[y] >> x) & 1)
    return out


def render40(page, alt, skip_flash=False):
    return render(page, None, alt, 40, skip_flash)


def shot(p):
    with urllib.request.urlopen(p.base + '/screen.ppm', timeout=10) as r:
        d = r.read()
    i = d.index(b'255\n') + 4
    px = d[i:]
    return [px[j * 3:j * 3 + 3] for j in range(len(px) // 3)]


def lit(pixels):
    return [int(px != b'\0\0\0') for px in pixels]


def colours(pixels):
    return len(set(pixels))


def same(expected, pixels):
    """Dots that differ (a different size: all of them), the don't-care
    ones left out."""
    got = lit(pixels)
    if len(got) != len(expected):
        return len(expected)
    return sum(1 for e, g in zip(expected, got) if e is not None and e != g)


def panels_as_drawn(p):
    """Dots of the screen that differ from the panels' text page rendered
    in the ALTERNATE set, the one A2FC's 80-column firmware leaves on; and
    how many bytes of that page ($40-$7F: MouseText, the mouse pointer)
    would show otherwise in the primary set -- 0 would make the check
    blind to the set."""
    main, aux = p.peek(0x400, 1024), p.peek(0x400, 1024, 'aux')
    telling = sum(1 for b in visible(main) + visible(aux) if 0x40 <= b < 0x80)
    return same(render(main, aux, True, 80), shot(p)), telling


def visible(mem):
    return bytes(mem[o] for o in VISIBLE)


def main():
    t40 = title()
    t80, _ = wide()
    pic = lores()
    files = {'WORK/A.TITLE#060400': t40, 'WORK/B.WIDE#060400': t80, 'WORK/C.LORES#060400': pic}
    with tempfile.TemporaryDirectory(prefix='a2fc-textscreen-') as tmp:
        # The mouse pointer is MouseText ($42): with it on the panels, a
        # character set left wrong after the viewer shows (enhanced only;
        # the 6502 edition has no mouse, tools/test_textscreen.py checks
        # RDALTCHAR is put back on both).
        with boot_hd(Path(tmp), files, port=7312, plugins=['dgrview'], mouse=FULL) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET)
            s.select('WORK'); s.key(RET); p.stable()
            s.select('A.TITLE'); p.stable()
            if FULL:
                p.mouse(dx=40, dy=20); p.stable()
            bad, telling = panels_as_drawn(p)
            s.ok('the panels on the air: the text page in the alternate set', bad == 0, f'{bad} dots differ')
            aux0 = p.peek(0, 0xC000, 'aux')
            main_holes = [p.peek(0x400 + o, 1)[0] for o in HOLES]

            # -- 40 columns ------------------------------------------------
            s.key(RET)
            s.wait(lambda: visible(p.peek(0x400, 1024)) == visible(t40), '40-column page', 60)
            p.stable()
            s.ok('40 columns: the page is in main', True)
            px = shot(p)
            s.ok('40 columns on the air, primary set, as the ROM draws it',
                 colours(px) == 2 and same(render40(t40, False, True), px) == 0,
                 f'{colours(px)} colours, {same(render40(t40, False, True), px)} dots differ')
            aux1 = p.peek(0, 0xC000, 'aux')
            diff = [a for a in range(0xC000) if aux1[a] != aux0[a]]
            # The core's "Loading NAME" screen is 80-column text: it writes
            # the visible AUX text page itself, before DGRVIEW runs.
            s.ok('40 columns: AUX untouched outside the visible text page',
                 all(0x400 <= a < 0x800 and (a - 0x400) % 128 < 120 for a in diff),
                 ' '.join('%04X' % a for a in diff[:12]))
            now = [p.peek(0x400 + o, 1)[0] for o in HOLES]
            changed = [(hex(0x400 + o), a, b) for o, a, b in zip(HOLES, main_holes, now) if a != b]
            # The file's hole bytes are $5A: none may have landed. (The
            # firmware keeps its own holes up to date meanwhile: the mouse's
            # slot 4, the 80-column firmware's $478 and $57B...)
            s.ok('40 columns: no hole byte of the file written into main',
                 all(b != 0x5A for _, a, b in changed), str(changed))
            s.key(b'A'); p.stable()
            px = shot(p)
            s.ok('A: the alternate set (MouseText where the primary flashes)',
                 same(render40(t40, True), px) == 0, f'{same(render40(t40, True), px)} dots differ')
            s.key(b'T'); p.stable()
            s.ok('T: the same bytes as lo-res', colours(shot(p)) > 2)
            s.ok('T writes nothing', visible(p.peek(0x400, 1024)) == visible(t40))
            s.key(b't'); p.stable()
            px = shot(p)
            s.ok('t again: text, the set chosen kept', same(render40(t40, True), px) == 0)
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux'), 'panels after the capture', 30); p.stable()
            if FULL:
                p.mouse(dx=-8, dy=-4); p.stable()
            bad, telling = panels_as_drawn(p)
            s.ok('Escape: the panels in the alternate set again',
                 bad == 0 and (telling > 0 or not FULL), f'{bad} dots differ, {telling} telling bytes')
            aux1 = p.peek(0, 0xC000, 'aux')
            s.ok('nothing of AUX written on the way but the visible text page',
                 aux1[:0x400] == aux0[:0x400] and aux1[0x800:] == aux0[0x800:]
                 and [aux1[0x400 + o] for o in HOLES] == [aux0[0x400 + o] for o in HOLES])

            # -- 80 columns ------------------------------------------------
            s.select('B.WIDE'); s.key(RET)
            h = len(t80) // 2
            s.wait(lambda: visible(p.peek(0x400, 1024, 'aux')) == visible(t80[:h])
                   and visible(p.peek(0x400, 1024)) == visible(t80[h:]), '80-column page', 60)
            p.stable()
            s.ok('80 columns: even columns in AUX, odd in main', True)
            aux1 = p.peek(0, 0xC000, 'aux')
            s.ok('80 columns: AUX written only in the visible $0400-$07FF',
                 aux1[:0x400] == aux0[:0x400] and aux1[0x800:] == aux0[0x800:]
                 and [aux1[0x400 + o] for o in HOLES] == [aux0[0x400 + o] for o in HOLES])
            px = shot(p)
            s.ok('80 columns on the air, alternate set, as the ROM draws it',
                 same(render(t80[h:], t80[:h], True, 80), px) == 0,
                 f'{same(render(t80[h:], t80[:h], True, 80), px)} dots differ')
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux'), 'panels after 80 columns', 30); p.stable()

            # -- a lo-res picture of the same metadata ---------------------
            s.select('C.LORES'); s.key(RET)
            s.wait(lambda: visible(p.peek(0x400, 1024)) == visible(pic), 'lo-res page', 60)
            p.stable()
            s.ok('a lo-res picture stays a picture', colours(shot(p)) > 2)
            s.key(b'T'); p.stable()
            s.ok('T reads the picture as text', colours(shot(p)) == 2)

            # -- neighbours: no panel text screen in between ----------------
            addr = s.sym['_switch_to_text']
            saved = p.peek(addr, 3)
            p.poke(addr, bytes([0x4C, addr & 255, addr >> 8]))
            try:
                s.key(LEFT, pause=0)
                s.wait(lambda: visible(p.peek(0x400, 1024)) == visible(t80[h:]), 'Left to 80 columns', 60)
                s.ok('Left: the 80-column neighbour, never the panels in between', True)
                s.key(LEFT, pause=0)
                s.wait(lambda: visible(p.peek(0x400, 1024)) == visible(t40), 'Left to 40 columns', 60)
                p.stable()
                px = shot(p)
                s.ok('Left: the 40-column neighbour on the air',
                     colours(px) == 2 and same(render40(t40, False, True), px) == 0)
            finally:
                p.poke(addr, saved)
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux'), 'final panels', 30); p.stable()
            bad, telling = panels_as_drawn(p)
            s.ok('Escape after the album: the panels, cursor on the first capture',
                 s.line().startswith('A.TITLE') and bad == 0, f'{bad} dots differ')
    return ok_all(s, 'textscreen')


if __name__ == '__main__':
    raise SystemExit(main())
