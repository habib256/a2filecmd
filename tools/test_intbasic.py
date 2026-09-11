"""List Integer BASIC with the actual overlay C, against a reference.

The $FA format is published but the corner that matters is not obvious: a
byte in $B0-$B9 introduces a sixteen-bit constant only OUTSIDE a string, a
REM and a name -- so the reference decoder below is written out in full and
the overlay is checked against it, on made-up programs and on the first six
lines of Woz's own Breakout, byte for byte off the disk.
"""
import base64
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
#include "src/plugins/intbasic.c"
static char screen[LINES][81];
static unsigned char hrow, hcol;
static void xy_(unsigned char x, unsigned char y) { hcol = x; hrow = y; }
static void putc_(char c) { if (hrow < LINES && hcol < 80) screen[hrow][hcol] = c; ++hcol; }
static void clear_(void)
{
    int r, c;
    for (r = 0; r < LINES; ++r) { for (c = 0; c < 80; ++c) screen[r][c] = ' '; screen[r][80] = 0; }
    hrow = hcol = 0;
}
int main(int argc, char** argv)
{
    static unsigned char data[512];
    int r = 1, rows;
    a.sprintf = sprintf; a.fread = fread; a.fseek = fseek;
    a.cputc = putc_; a.gotoxy = xy_; buf = data;
    f = fopen(argv[1], "rb");
    clear_();
    seek(0);
    row = col = 0; space = 1;
    while (row < LINES && r == 1) r = line();
    printf("STATUS %d\n", r);
    for (rows = LINES - 1; rows >= 0; --rows) {          /* trailing blanks away */
        int c = 79;
        while (c >= 0 && screen[rows][c] == ' ') --c;
        if (c >= 0) break;
    }
    for (r = 0; r <= rows; ++r) {
        int c = 79;
        while (c >= 0 && screen[r][c] == ' ') --c;
        screen[r][c + 1] = 0;
        printf("%s\n", screen[r]);
    }
    fclose(f);
    return 0;
}
"""

TOK = [
    "HIMEM:", "", "_", ":", "LOAD", "SAVE", "CON", "RUN",
    "RUN", "DEL", ",", "NEW", "CLR", "AUTO", ",", "MAN",
    "HIMEM:", "LOMEM:", "+", "-", "*", "/", "=", "#",
    ">=", ">", "<=", "<>", "<", "AND", "OR", "MOD",
    "^", "+", "(", ",", "THEN", "THEN", ",", ",",
    '"', '"', "(", "!", "!", "(", "PEEK", "RND",
    "SGN", "ABS", "PDL", "RNDX", "(", "+", "-", "NOT",
    "(", "=", "#", "LEN(", "ASC(", "SCRN(", ",", "(",
    "$", "$", "(", ",", ",", ";", ";", ";",
    ",", ",", ",", "TEXT", "GR", "CALL", "DIM", "DIM",
    "TAB", "END", "INPUT", "INPUT", "INPUT", "FOR", "=", "TO",
    "STEP", "NEXT", ",", "RETURN", "GOSUB", "REM", "LET", "GOTO",
    "IF", "PRINT", "PRINT", "PRINT", "POKE", ",", "COLOR=", "PLOT",
    ",", "HLIN", ",", "AT", "VLIN", ",", "AT", "VTAB",
    "=", "=", ")", ")", "LIST", ",", "LIST", "POP",
    "NODSP", "NODSP", "NOTRACE", "DSP", "DSP", "TRACE", "PR#", "IN#",
]


def listing(d):
    """The reference lister: the rule written out, spacing included."""
    out, i = [], 0
    while i < len(d):
        ln = d[i]
        num = d[i + 1] | (d[i + 2] << 8)
        line = '%d ' % num
        j, alnum = i + 3, False
        while j < i + ln:
            c = d[j]
            if c == 0x01:
                break
            if c in (0x28, 0x29):
                line += '"'
                j += 1
                while j < i + ln and d[j] != 0x29:
                    line += chr(d[j] & 0x7F); j += 1
                line += '"'; j += 1; alnum = False
                continue
            if c == 0x5D:
                line += ' REM ' if not line.endswith(' ') else 'REM '
                j += 1
                while j < i + ln and d[j] != 0x01:
                    line += chr(d[j] & 0x7F); j += 1
                break
            if 0xB0 <= c <= 0xB9 and not alnum:
                line += str(d[j + 1] | (d[j + 2] << 8)); j += 3; alnum = True
                continue
            if c & 0x80:
                ch = chr(c & 0x7F)
                line += ch
                alnum = ch.isalnum()
                j += 1
                continue
            t = TOK[c]
            if t[:1].isalpha() and not line.endswith(' '):
                line += ' '
            line += t
            if t[-1:].isalpha():
                line += ' '
            alnum = False
            j += 1
        out.append(line.rstrip())
        i += ln
    return out


def wrapped(lines):
    """The same listing as it lands on an 80-column screen: a logical line
    longer than 80 characters is carried on to the next row."""
    out = []
    for l in lines:
        while len(l) > 80:
            out.append(l[:80].rstrip())
            l = l[80:]
        out.append(l.rstrip())
    return out


def prog(lines):
    """A program from (number, body bytes) pairs, with the length bytes put
    on for us."""
    out = bytearray()
    for num, body in lines:
        rec = bytes([num & 0xFF, num >> 8]) + body + b'\x01'
        out += bytes([len(rec) + 1]) + rec
    return bytes(out)


def chars(s):
    return bytes(ord(c) | 0x80 for c in s)


def const(v):
    """A constant: its leading digit, then the sixteen-bit value."""
    return bytes([0xB0 + int(str(v)[0])]) + bytes([v & 0xFF, v >> 8])


BREAKOUT = base64.b64decode(   # the first six lines of WOZ.BREAKOUT, off the disk
    'MAUASwNNNrmoAwNvtAQAA1CxCgADYSiqqqqgwtLFwcvP1dSgx8HNxaCqqqopA2MBQwcAYSigoM/C'
    'ysXD1KDJ06DUz6DExdPU0s/ZoMHMzKDC0snDy9Og18nUyKC1oMLBzMzTKQNVzlaxAQBXt1gbA1nO'
    'AWsKAE7BQCKyFAByQ8JAIrIUAHIDTANjA1MoyMmsoNfIwdSn06DZz9XSoM7BzcW/oCkmwUADwXGx'
    'AQADwnGxDQADw3G5CQADxHG2BgADxXGxDwADYSjT1MHOxMHSxKDDz8zP0tOsKUXBQEcBRRQAUyi/'
    'oCkmwkADYMJAOijOKR3CQDoozs8pJLMeAANVyVawAABXsycAA2bJFbICABQ4yRyzIAByA2ywAABt'
    'sycAbskBWhkAWckDZLMiAGWyFAADYwNjA2MDVclWsAAAV7EPAANvshUAEskfsgIAA1DJEskSsQEA'
    'A2LJRwNZyQNksyIAZbIWAANvshgAA2MDYSjCwcPLx9LP1c7EKUcBXRsAXLFkAAPBccUDYSjF1sXO'
    'oMLSycPLKUcDXLFkAAPCccUDYSjPxMSgwtLJw8spRwNcsWQAA8NxxQNhKNDBxMTMxSlHA1yxZAAD'
    'xHHFA2EowsHMzClHA1yxZAAB')


class IntBasic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='intbasic-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_list(self, data):
        f = self.p / 'in.bin'
        f.write_bytes(data)
        r = subprocess.run([str(self.exe), str(f)], capture_output=True, text=True)
        out = r.stdout.splitlines()
        status = int(out[0].split()[1])
        return status, out[1:]

    def test_a_token_and_a_constant(self):
        st, lines = self.run_list(prog([(10, bytes([0x6F]) + const(4))]))
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['10 VTAB 4'])

    def test_a_digit_after_a_letter_is_part_of_the_name(self):
        """A1 is two characters, not A and a constant: the $B1 follows a
        letter, so it is a digit of the name."""
        body = chars('A1') + bytes([0x39]) + const(7)
        st, lines = self.run_list(prog([(20, body)]))
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['20 A1=7'])

    def test_a_digit_in_a_string_is_a_character(self):
        """The bug this replaced: "WITH 5 BALLS" came out "WITH 49824ALLS"
        because the $B5 was read as a constant."""
        body = bytes([0x61, 0x28]) + chars('WITH 5 BALLS') + bytes([0x29])
        st, lines = self.run_list(prog([(30, body)]))
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['30 PRINT "WITH 5 BALLS"'])

    def test_a_rem_runs_to_the_end_of_the_line(self):
        body = bytes([0x5D]) + chars(' 3 OF A KIND: NOT A TOKEN')
        st, lines = self.run_list(prog([(40, body)]))
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['40 REM  3 OF A KIND: NOT A TOKEN'])

    def test_the_spacing_is_the_interpreters(self):
        """A space before a keyword that starts with a letter and after one
        that ends with a letter, none around the punctuation."""
        body = bytes([0x4C, 0x03, 0x61, 0x03, 0x52]) + chars('A$')
        st, lines = self.run_list(prog([(50, body)]))
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['50 GR : PRINT : INPUT A$'])

    def test_several_lines_in_order(self):
        p = prog([(1, bytes([0x4B])), (2, bytes([0x51])), (3, bytes([0x5F]) + const(1))])
        st, lines = self.run_list(p)
        self.assertEqual(st, 0)
        self.assertEqual(lines, wrapped(listing(p)))

    def test_a_constant_counts_as_three_bytes_of_the_record(self):
        """The length byte says where the NEXT record starts, so a constant
        has to be charged all three of its bytes: charge it one and a line
        with no $01 of its own reads on into its neighbour."""
        p = (bytes([6, 10, 0]) + const(7)          # no $01: the length ends it
             + bytes([5, 20, 0, 0x4B, 0x01]))
        st, lines = self.run_list(p)
        self.assertEqual(st, 0)
        self.assertEqual(lines, ['10 7', '20 TEXT'])

    def test_a_record_running_past_the_end_is_refused(self):
        p = prog([(10, bytes([0x4B]))])
        st, _ = self.run_list(p[:-1])
        self.assertEqual(st, 2)

    def test_a_length_byte_too_small_is_refused(self):
        self.assertEqual(self.run_list(b'\x02\x0a\x00')[0], 2)

    def test_an_empty_file_lists_nothing(self):
        st, lines = self.run_list(b'')
        self.assertEqual(st, 0)
        self.assertEqual(lines, [])

    # -- the real thing ----------------------------------------------------
    def test_the_first_lines_of_breakout(self):
        """Woz's own Breakout, off the disk: the overlay must reproduce the
        listing the interpreter prints."""
        st, lines = self.run_list(BREAKOUT)
        self.assertEqual(st, 0)
        self.assertEqual(lines, wrapped(listing(BREAKOUT)))
        self.assertEqual(lines[0],
                         '5 TEXT : CALL -936: VTAB 4: TAB 10: PRINT "*** BREAKOUT GAME ***": PRINT')
        self.assertIn('WITH 5 BALLS', lines[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
