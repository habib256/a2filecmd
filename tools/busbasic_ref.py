#!/usr/bin/env python3
"""Business BASIC (BA3, $09): the reference for BASLIST's Apple /// listing.

    busbasic_ref.py FILE        # prints the lines BASLIST shows
    busbasic_ref.py --selftest

The format (CiderPress II's BASIC notes): a 2-byte length, then lines of a
length byte (0 ends the program), a 16-bit line number, bytes -- tokens
from $80, $FF followed by an extended token -- and a zero. BASLIST prints
"NUMBER ", then each token as " NAME " (an unknown one as " ? "), each
other byte with its high bit cleared. The token names are read from
src/a2fc.c's BB_TOK and BB_EXT, the tables BASLIST prints from.
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src/a2fc.c'


def _table(name):
    src = SRC.read_text()
    m = re.search(r'static const char %s\[\] =\n((?:\s*".*"\n?)+);' % name, src)
    body = ''.join(re.findall(r'"(.*?)"', m.group(1)))
    return body.encode().decode('unicode_escape').split('\0')


TOK = _table('BB_TOK')[:128]
EXT = _table('BB_EXT')[:84]


def name(table, n):
    return table[n] if n < len(table) and table[n] else '?'


def listing(data):
    """The listing's lines, and whether the program's end was reached."""
    lines, i = [], 2
    while True:
        if i >= len(data):
            return lines, True          # EOF counts as the end, as view_getc says
        if data[i] == 0:
            return lines, True
        i += 1
        if i + 2 > len(data):
            return lines, True
        num = data[i] | data[i + 1] << 8
        i += 2
        out = '%u ' % num
        while i < len(data):
            t = data[i]
            i += 1
            if t == 0:
                break
            if t >= 0x80:
                if t == 0xFF:
                    if i >= len(data):
                        break
                    word = name(EXT, data[i] & 0x7F)
                    i += 1
                else:
                    word = name(TOK, t - 0x80)
                out += ' %s ' % word
            else:
                out += chr(t & 0x7F)
        lines.append(out)


def make(lines):
    """A BA3 file from [(number, bytes)] (tests)."""
    body = bytearray()
    for num, code in lines:
        rec = bytes(num.to_bytes(2, 'little')) + bytes(code) + b'\0'
        body += bytes([len(rec) + 1]) + rec
    body += b'\0\0'
    return len(body).to_bytes(2, 'little') + bytes(body)


def selftest():
    assert TOK[0] == 'END' and TOK[0x19] == 'HPOS' and TOK[0x7F] == ''
    assert EXT[0x1D] == 'SGN(' and EXT[0x53] == 'INSTR('
    data = make([(10, b'\xc0 HELLO'), (20, b'\xd9"X"\xff\x9d1)'), (30, b'\x8a\xfe')])
    lines, end = listing(data)
    assert lines == ['10  REM  HELLO', '20  PRINT "X" SGN( 1)', '30  ?  ? '], lines
    assert end
    print('selftest: tables, lines, unknown tokens')


def main():
    if sys.argv[1:] == ['--selftest']:
        selftest()
        return 0
    lines, end = listing(Path(sys.argv[1]).read_bytes())
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
