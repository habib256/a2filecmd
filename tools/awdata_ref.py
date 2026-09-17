#!/usr/bin/env python3
"""AppleWorks data bases ($19) and spreadsheets ($1B): the reference for the
AWDATA viewer.

    awdata_ref.py FILE [--type 19|1b]     # prints what the viewer shows
    awdata_ref.py --selftest

The layouts follow CiderPress II's converters (FileConv/Doc/AppleWorksDB.cs
and AppleWorksSS.cs, after Apple's File Type Notes $19 and $1B):

Data base: the category count at +35, the record count at +36 (15 bits),
the report count at +38; category names from +357, 22 bytes each (a length,
then up to 20 characters); then the reports, 600 bytes each; then records,
each a 2-byte length and category entries -- a control byte $01-$7F and
that many bytes, $81-$9E skipping (n - $80) categories, $FF ending it. The
first record holds the standard values and is not shown. A 6-byte entry
starting $C0 is a date (year, month letter, day), a 4-byte one starting $D4
a time (hour letter, minutes). $FF $FF ends the records.

Spreadsheet: a 300-byte header, two more bytes when the version at +242 is
not 0; then rows, each a 2-byte length ($FFFF ends them), a row number and
cells -- a control byte $01-$7F and that many bytes, $81-$FE skipping
(n - $80) columns, $FF ending the row. A cell's first byte says label
(bit 7 clear: text, or bit 5 one character repeated 8 times) or value
(bit 5: an 8-byte double; otherwise a formula, after the cached result --
or, with bit 3 of the second byte, after a cached display string).
Formulas are tokens from $C0 up: functions and operators, $FD a double,
$FE a relative cell reference, $FF a string.

What the viewer shows, 80 columns:
  data base  -- one record at a time, a row per category: the name padded to
               20, a space, the value; 22 rows, TAB for categories 23-30.
  spreadsheet -- a row per cell: the reference padded to 7, then the text,
               the number, or the formula followed by "  = " and its result.
Numbers go through Applesoft's FOUT, from the ROM: `mbf()` is the 5-byte
number the viewer hands it, `fout()` what FOUT prints.
"""
import argparse
import random
import re
import struct
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROWS = 22
WIDTH = 79

TOKENS = [
    '@Deg', '@Rad', '@Pi', '@True', '@False', '@Not', '@IsBlank', '@IsNA',
    '@IsError', '@Exp', '@Ln', '@Log', '@Cos', '@Sin', '@Tan', '@ACos',
    '@ASin', '@ATan2', '@ATan', '@Mod', '@FV', '@PV', '@PMT', '@Term',
    '@Rate', '@Round', '@Or', '@And', '@Sum', '@Avg', '@Choose', '@Count',
    '@Error', '@IRR', '@If', '@Int', '@Lookup', '@Max', '@Min', '@NA',
    '@NPV', '@Sqrt', '@Abs', '', '<>', '>=', '<=', '=',
    '>', '<', ',', '^', ')', '-', '+', '/',
    '*', '(', '-', '+', '...', '', '', '']
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


class Bad(ValueError):
    pass


def char(c):
    """An AppleWorks character as the viewer prints it."""
    if c < 0x20:
        return '?'
    if c < 0x80:
        return chr(c)
    if c < 0xA0:
        return chr(c - 0x40)
    if c < 0xC0:
        return chr(c - 0x80)
    if c < 0xE0:
        return '?'                  # MouseText
    return chr(c - 0x80)


def text(b):
    return ''.join(char(c) for c in b)


def mbf(d):
    """The packed Applesoft number for the double d (8 bytes, little-endian),
    or None when Applesoft cannot hold it."""
    e = ((d[7] & 0x7F) << 4) | (d[6] >> 4)
    if e == 0:
        return bytes(5)
    if e == 0x7FF:
        return None
    m = (0x80000000 | ((d[6] & 15) << 27) | (d[5] << 19) | (d[4] << 11)
         | (d[3] << 3) | (d[2] >> 5))
    if (d[2] >> 4) & 1:
        m += 1
        if m == 1 << 32:
            m = 0x80000000
            e += 1
    x = e - 894
    if x < 1 or x > 255:
        return None
    return bytes([x, ((m >> 24) & 0x7F) | (d[7] & 0x80), (m >> 16) & 255, (m >> 8) & 255, m & 255])


def mbf_value(p):
    if p[0] == 0:
        return Decimal(0)
    m = ((p[1] | 0x80) << 24) | (p[2] << 16) | (p[3] << 8) | p[4]
    v = Decimal(m) * Decimal(2) ** (p[0] - 128 - 32)
    return -v if p[1] & 0x80 else v


def fout(p):
    """What Applesoft's FOUT prints for the packed number p: nine significant
    digits, no trailing zeros, no leading zero, E notation below .01 and
    from 1E+09."""
    v = mbf_value(p)
    if v == 0:
        return '0'
    sign = '-' if v < 0 else ''
    v = abs(v)
    exp = v.adjusted()
    digits = v.scaleb(-exp).quantize(Decimal('1.00000000'), rounding=ROUND_HALF_UP)
    if digits >= 10:
        digits = (digits / 10).quantize(Decimal('1.00000000'), rounding=ROUND_HALF_UP)
        exp += 1
    ds = ('%.8f' % digits).replace('.', '').rstrip('0')
    if exp < -2 or exp > 8:
        mant = ds[0] + ('.' + ds[1:] if len(ds) > 1 else '')
        return '%s%sE%s%02d' % (sign, mant, '-' if exp < 0 else '+', abs(exp))
    if exp < 0:
        return sign + '.' + '0' * (-exp - 1) + ds
    if len(ds) <= exp + 1:
        return sign + ds + '0' * (exp + 1 - len(ds))
    return sign + ds[:exp + 1] + '.' + ds[exp + 1:]


def same_number(shown, want):
    """Whether FOUT's text `shown` is the reference's `want`, but for the
    ninth digit: the ROM's decimal conversion rounds it its own way, one
    unit off now and then."""
    if shown == want:
        return True
    if ('E' in shown) != ('E' in want) or shown[:1] != want[:1] or '#' in shown + want:
        return False
    try:
        a, b = float(shown), float(want)
    except ValueError:
        return False
    return abs(a - b) <= 1.5e-8 * max(abs(a), abs(b))


NUMBER = re.compile(r'-?(?:\d+\.?\d*|\.\d+)(?:E[-+]\d\d)?')


def same_line(shown, want):
    """A screen line against the reference, numbers compared by same_number."""
    if shown == want:
        return True
    if NUMBER.split(shown) != NUMBER.split(want):
        return False
    return all(same_number(a, b) for a, b in zip(NUMBER.findall(shown), NUMBER.findall(want)))


def number(d):
    p = mbf(d)
    return '#NUM' if p is None else FOUT(p)


FOUT = fout         # the host test replaces it with the host build's stand-in


# -- data base -------------------------------------------------------------

def db_header(data):
    if len(data) < 381:
        raise Bad('short')
    ncats = data[35]
    if not 1 <= ncats <= 30:
        raise Bad('categories')
    names = []
    for i in range(ncats):
        o = 357 + 22 * i
        n = data[o]
        if n > 20:
            raise Bad('category name')
        names.append(text(data[o + 1:o + 1 + n]))
    first = 357 + 22 * ncats + 600 * data[38]
    return names, first


def db_date(b):
    if len(b) != 6 or not 0 <= b[3] - 65 <= 11:
        return '#BAD DATE#'
    out = ''
    day = b[4:6].replace(b' ', b'0')
    if day != b'00':
        out = text(day) + ' '
    out += MONTHS[b[3] - 65]
    if b[1:3] != b'00':
        out += ' ' + text(b[1:3])
    return out


def db_time(b):
    h = b[1] - 65
    if not 0 <= h <= 23 or not all(48 <= c <= 57 for c in b[2:4]):
        return '#BAD TIME#'
    ampm = 'AM' if h < 12 else 'PM'
    h = h % 12 or 12
    return '%d:%s %s' % (h, text(b[2:4]), ampm)


def db_record(rec, ncats):
    """The values of one record's categories."""
    values = [''] * ncats
    cat, i = 0, 0
    while i < len(rec):
        c = rec[i]
        i += 1
        if c == 0xFF:
            break
        if 1 <= c <= 0x7F:
            if i + c > len(rec):
                break                   # an entry past its record ends it
            b = rec[i:i + c]
            i += c
            if cat < ncats:
                if c == 6 and b[0] == 0xC0:
                    values[cat] = db_date(b)
                elif c == 4 and b[0] == 0xD4:
                    values[cat] = db_time(b)
                else:
                    values[cat] = text(b)
        elif 0x81 <= c <= 0x9E:
            cat += c - 0x81
        else:
            break
        cat += 1
    return values


def db_records(data):
    """[(values)] of the shown records (the standard values record skipped),
    and whether the $FFFF end was reached."""
    names, o = db_header(data)
    out = []
    first = True
    while True:
        if o + 2 > len(data):
            return names, out, False
        n = data[o] | data[o + 1] << 8
        if n == 0xFFFF:
            return names, out, True
        if n == 0 or o + 2 + n > len(data):
            return names, out, False
        if not first:
            out.append(db_record(data[o + 2:o + 2 + n], len(names)))
        first = False
        o += 2 + n


def db_screen(names, values, first=0):
    rows = []
    for k in range(first, min(first + ROWS, len(names))):
        rows.append(('%-20s %s' % (names[k], values[k]))[:WIDTH])
    return rows


# -- spreadsheet -------------------------------------------------------------

def col_name(c):
    if not 0 <= c <= 127:
        return '#ERR#'
    if c < 26:
        return chr(65 + c)
    return chr(64 + c // 26) + chr(65 + c % 26)


def formula(b, col, row):
    # A token's operands past the cell read as zeros; a string stops there.
    end, b = len(b), b + bytes(12)
    out, i = '', 0
    while i < end:
        t = b[i]
        i += 1
        if t < 0xC0:
            continue
        out += TOKENS[t - 0xC0]
        if t in (0xE0, 0xE7):
            i += 3
        elif t == 0xFD:
            out += number(b[i:i + 8])
            i += 8
        elif t == 0xFE:
            dc = struct.unpack('<b', b[i:i + 1])[0]
            dr = struct.unpack('<h', b[i + 1:i + 3])[0]
            r = (row + dr) & 0xFFFF                 # 16 bits, printed signed
            out += col_name(col + dc) + str(r - 0x10000 if r & 0x8000 else r)
            i += 3
        elif t == 0xFF:
            n = b[i]
            out += '"' + text(b[i + 1:min(i + 1 + n, end)]) + '"'
            i += 1 + n
    return out


def ss_cell(b, col, row):
    # Fixed fields past the cell read as zeros; text stops at its end.
    end, z = len(b), b + bytes(11)
    f = b[0]
    if f & 0x80:
        if f & 0x20:
            return number(z[2:10])
        if z[1] & 0x08:
            n = z[2]
            shown = text(b[3:3 + n])
            return formula(b[3 + n:], col, row) + '  = ' + shown
        return formula(b[10:], col, row) + '  = ' + number(z[2:10])
    if f & 0x20:
        return char(z[1]) * 8
    return text(b[1:end])


def ss_lines(data):
    """Every line the viewer shows, and whether the $FFFF end was reached."""
    if len(data) < 302:
        raise Bad('short')
    o = 302 if data[242] else 300
    lines = []
    while True:
        if o + 2 > len(data):
            return lines, False
        n = data[o] | data[o + 1] << 8
        if n == 0xFFFF:
            return lines, True
        if n < 2 or o + 2 + n > len(data):
            return lines, False
        rec = data[o + 2:o + 2 + n]
        row = rec[0] | rec[1] << 8
        col, i = 0, 2
        while i < len(rec):
            c = rec[i]
            i += 1
            if c == 0xFF:
                break
            if c <= 0x7F:
                if c == 0 or i + c > len(rec):
                    break
                ref = '%s%u' % (col_name(col), row)
                lines.append(('%-7s%s' % (ref, ss_cell(rec[i:i + c], col, row)))[:WIDTH])
                i += c
            else:
                col += c - 0x81
            col += 1
        o += 2 + n


# -- self test ---------------------------------------------------------------

def selftest():
    cases = {0.5: '.5', 1.0: '1', -2.25: '-2.25', 100.0: '100', 0.01: '.01',
             0.001: '1E-03', 123456789.0: '123456789', 1e9: '1E+09',
             1234567891.0: '1.23456789E+09', 1 / 3: '.333333333', 0.1: '.1',
             -1e-10: '-1E-10', 2.0 ** 100: '1.2676506E+30', 0.0: '0'}
    for v, want in cases.items():
        got = number(struct.pack('<d', v))
        assert got == want, (v, got, want)
    assert number(struct.pack('<d', 1e300)) == '#NUM'
    assert col_name(0) == 'A' and col_name(25) == 'Z' and col_name(26) == 'AA'
    assert col_name(127) == 'DX' and col_name(-1) == '#ERR#'
    assert db_date(b'\xc070A05') == '05 Jan 70'
    assert db_date(b'\xc000L 0') == 'Dec' and db_date(b'\xc099Z01') == '#BAD DATE#'
    assert db_time(b'\xd4A05') == '12:05 AM' and db_time(b'\xd4N30') == '1:30 PM'
    rng = random.Random(1)
    for _ in range(2000):
        v = rng.uniform(-1e12, 1e12) * 10 ** rng.randint(-20, 0)
        p = mbf(struct.pack('<d', v))
        assert p is not None
        assert abs(float(mbf_value(p)) - v) <= abs(v) * 2 ** -31, v
    print('selftest: numbers, columns, dates and times')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file', nargs='?')
    ap.add_argument('--type', default='19')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    data = Path(args.file).read_bytes()
    if args.type == '19':
        names, recs, end = db_records(data)
        for k, values in enumerate(recs):
            print('-- record %d of %d' % (k + 1, len(recs)))
            print('\n'.join(db_screen(names, values)))
    else:
        lines, end = ss_lines(data)
        print('\n'.join(lines))
    if not end:
        print('-- (cut)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
