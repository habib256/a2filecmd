#!/usr/bin/env python3
"""Text screen or lo-res picture: DGRVIEW's decision, in Python.

A saved page of the Apple II -- a BIN at aux $0400, or 1,024/2,048 bytes --
is a lo-res (double lo-res) picture or a TEXT screen, and nothing in its
metadata says which: bmp2dhr's .SLO and a BSAVE of a title screen are the
same file to ProDOS. src/plugins/dgrview.c (looks_text) decides by content;
this is the same rule, written out so that tools/test_textscreen.py can hold
the C to it and measure it on real files of both kinds.

    textscreen_ref.py FILE...    prints the verdict, the counts, and the
                                 page as the Apple II's 40 or 80 columns

The counts are taken over the VISIBLE bytes only (the screen holes are the
cards' and hold anything), of each half for an 80-column page (more than
1,024 bytes: the auxiliary half first, len/2 each, as DGRVIEW lays it):
  blank  a space: $A0 normal, $20 inverse, $E0 (a space on the II+);
  solid  a byte whose two nibbles are equal: two stacked pixels of one
         colour in lo-res, what every flat area of a picture is made of.
"""
import sys


def row_of(r):
    """The page offset of text row r, 0..23."""
    return (r & 7) * 128 + (r >> 3) * 40


def halves(data):
    """The one or two halves of a saved page, as DGRVIEW splits it."""
    if len(data) > 1024:
        h = len(data) >> 1
        return [data[:h], data[h:2 * h]]
    return [data]


def visible(half):
    """The visible bytes of a half, row by row (a short file: what it has)."""
    out = bytearray()
    for r in range(24):
        at = row_of(r)
        out += half[at:at + 40]
    return bytes(out)


def counts(data):
    blank = solid = seen = 0
    for h in halves(data):
        for b in visible(h):
            seen += 1
            blank += b in (0x20, 0xA0, 0xE0)
            solid += (b >> 4) == (b & 15)
    return blank, solid, seen


def rule(blank, solid, seen):
    """TEXT_RULE in dgrview.c."""
    return blank * 4 >= seen and blank > solid


def looks_text(data):
    return rule(*counts(data))


def char(b, alt=False):
    """The glyph of a screen byte, as close as ASCII gets (inverse and
    flashing shown plain): primary set, or the alternate one, where $40-$5F
    is MouseText (shown '#') and $60-$7F inverse lower case."""
    if alt and 0x40 <= b < 0x60:
        return '#'
    if alt and 0x60 <= b < 0x80:
        c = b
    elif b < 0x20 or 0x80 <= b < 0xA0:
        c = (b & 0x1F) | 0x40               # @ A-Z [ \ ] ^ _
    elif b < 0x40 or 0x60 <= b < 0x80:
        c = (b & 0x1F) | 0x20 if b >= 0x60 else b   # space ! " ... ?
    else:
        c = b & 0x7F
    return chr(c) if 0x20 <= c < 0x7F else '.'


def render(data, alt=None):
    """The page as text lines: 40 columns, or 80 for two halves (even
    columns from the auxiliary half)."""
    hs = halves(data)
    if alt is None:
        alt = len(hs) == 2
    lines = []
    for r in range(24):
        at = row_of(r)
        if len(hs) == 1:
            row = hs[0][at:at + 40]
            lines.append(''.join(char(b, alt) for b in row))
        else:
            a, m = hs[0][at:at + 40], hs[1][at:at + 40]
            lines.append(''.join(char(x, alt) + char(y, alt) for x, y in zip(a, m)))
    return lines


def main(argv):
    for name in argv[1:]:
        data = open(name, 'rb').read()
        blank, solid, seen = counts(data)
        verdict = 'text' if rule(blank, solid, seen) else 'lo-res'
        print(f'{name}: {len(data)} bytes, {verdict} (blank {blank}, solid {solid}, of {seen})')
        for line in render(data):
            print('  |' + line + '|')


if __name__ == '__main__':
    main(sys.argv)
