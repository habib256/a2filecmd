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
static long host_fail = -1;                 /* a read error from this offset on */
static int host_err;
#define ferror(f) (host_err)
#include "src/plugins/intbasic.c"
static size_t rd_(void* p, size_t z, size_t n, FILE* h)
{
    long at = ftell(h);
    if (host_fail >= 0 && at + (long)n > host_fail) {
        if (at >= host_fail) { host_err = 1; return 0; }
        n = host_fail - at;               /* what comes before the bad block */
    }
    return fread(p, z, n, h);
}
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
static void show(int r)
{
    int n, c;
    printf("PAGE %d %ld %u\n", r, r == 1 ? (long)next : -1L, first + page);
    for (n = 0; n < LINES; ++n) {
        c = 79;
        while (c >= 0 && screen[n][c] == ' ') --c;
        screen[n][c + 1] = 0;
        printf("|%s\n", screen[n]);
    }
}
/* argv[2]: page through listpage() from that offset, as Space does
 * (forward()); argv[3] "back": then back to the oldest page kept, as B
 * does; argv[4]: a read error from that offset on. */
static void pages(unsigned long from, int back)
{
    int r;
    starts[0] = from; page = head = 0; known = 1; first = 1;
    for (;;) {
        r = listpage();
        show(r);
        if (r != 1) break;
        forward();
    }
    if (!back) return;
    while (page) {
        --page;
        show(listpage());
    }
}
int main(int argc, char** argv)
{
    static unsigned char data[512];
    int r = 1, rows;
    a.sprintf = sprintf; a.fread = rd_; a.fseek = fseek;
    a.cputc = putc_; a.gotoxy = xy_; a.clrscr = clear_; buf = data;
    f = fopen(argv[1], "rb");
    if (argc > 4) host_fail = atol(argv[4]);
    if (argc > 2) { pages(strtoul(argv[2], 0, 10), argc > 3 && !strcmp(argv[3], "back")); return 0; }
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


def paged(lines, rows=22):
    """The pages as they must come: whole lines while they fit; a line that
    runs off the bottom is started there and shown again, whole, at the top
    of the next page (unless it began its own page, which it then fills)."""
    pages, i = [], 0
    while i < len(lines):
        page, first = [], i
        while i < len(lines) and len(page) < rows:
            w = wrapped([lines[i]])
            if len(page) + len(w) > rows:
                page += w[:rows - len(page)]
                if i != first:
                    break
            else:
                page += w
            i += 1
        pages.append(page)
    return pages


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

    # -- pages -------------------------------------------------------------
    def run_pages(self, data, start=0, back=False, fail=None, numbers=False):
        f = self.p / 'in.bin'
        f.write_bytes(data)
        args = [str(start), 'back' if back else '-'] + ([str(fail)] if fail is not None else [])
        out = subprocess.check_output([str(self.exe), str(f)] + args, text=True, timeout=60)
        pages = []
        for l in out.splitlines():
            if l.startswith('PAGE '):
                _, r, nxt, num = l.split()
                pages.append((int(r), int(nxt), [], int(num)))
            else:
                pages[-1][2].append(l[1:])
        for _, _, rows, _ in pages:
            while rows and not rows[-1]:
                rows.pop()
        return pages if numbers else [p[:3] for p in pages]

    def test_a_long_line_at_the_bottom_is_shown_whole_on_the_next_page(self):
        """The tail of a line wrapped past row 21 used to be skipped: the
        next page started after the line."""
        p = prog([(i, bytes([0x4B])) for i in range(1, 21)]
                 + [(100, bytes([0x5D]) + chars('X' * 200))] + [(200, bytes([0x51]))])
        pages = self.run_pages(p)
        self.assertEqual([rows for _, _, rows in pages], paged(listing(p)))
        self.assertTrue(pages[1][2][0].startswith('100 REM XXX'))
        self.assertEqual(pages[1][2][3], '200 END')

    def test_every_row_of_every_line_is_shown_at_every_offset(self):
        for lead in range(0, 23):
            for size in (60, 77, 78, 150, 157, 158, 237, 240):
                body = [(i, bytes([0x4B])) for i in range(1, lead + 1)]
                body += [(1000 + k, bytes([0x5D]) + chars(chr(65 + k) * size)) for k in range(12)]
                p = prog(body)
                with self.subTest(lead=lead, size=size):
                    pages = self.run_pages(p)
                    self.assertTrue(all(r in (0, 1) for r, _, _ in pages))
                    self.assertEqual([rows for _, _, rows in pages if rows], paged(listing(p)))

    def test_page_offsets_past_64k(self):
        """Offsets are 24-bit in ProDOS: a page starting past 65,535 must
        read from there, and the next page's start must not wrap."""
        p = prog([(i + 1, bytes([0x4B])) for i in range(14000)])    # 5 bytes a line
        self.assertEqual(len(p), 70000)
        (r, nxt, rows), = self.run_pages(p, 66000)[:1]
        self.assertEqual(r, 1)
        self.assertEqual(rows[0], '13201 TEXT')
        self.assertEqual(rows[21], '13222 TEXT')
        self.assertEqual(nxt, 66110)

    def test_past_the_old_page_limit(self):
        """A listing of 91 pages goes to its end, and B goes back 63.

        Before: starts[] held 40 pages and the 41st was never recorded: at
        page 40 Space did nothing and "(end)" never showed -- the rest of
        the program could not be listed, and nothing said so. Now the
        starts are a ring of 64, as in MDVIEW."""
        p = prog([(i + 1, bytes([0x4B])) for i in range(2000)])
        want = paged(listing(p))
        self.assertEqual(len(want), 91)
        pages = self.run_pages(p, back=True, numbers=True)
        fwd, back = pages[:91], pages[91:]
        self.assertEqual([rows for _, _, rows, _ in fwd], want)
        self.assertEqual([n for _, _, _, n in fwd], list(range(1, 92)))
        self.assertEqual([r for r, _, _, _ in fwd], [1] * 90 + [0])
        self.assertEqual(fwd[-1][2][-1], '2000 TEXT')
        # back: pages 90 down to 28, the oldest of the 64 kept
        self.assertEqual([n for _, _, _, n in back], list(range(90, 27, -1)))
        self.assertEqual([rows for _, _, rows, _ in back], want[89:26:-1])

    def test_a_read_error_is_not_the_end(self):
        """A block that cannot be read: the page stops there with r = 3.

        Before: getb took fread's 0 for the end of the file without
        ferror(): the listing ended with "(end)" (or "ends in the middle
        of a line") as if the program were whole."""
        p = prog([(i + 1, bytes([0x5D]) + chars('LINE %d' % i)) for i in range(300)])
        whole = self.run_pages(p)
        self.assertEqual(whole[-1][0], 0)
        for fail in (0, 3, 254, 255, 600, 2000, len(p) - 1):
            with self.subTest(fail=fail):
                pages = self.run_pages(p, fail=fail)
                self.assertEqual(pages[-1][0], 3)
                self.assertTrue(all(r == 1 for r, _, _ in pages[:-1]))
                shown = [l for _, _, rows in pages for l in rows]
                ref = [l for _, _, rows in whole for l in rows]
                self.assertEqual(shown[:-1], ref[:max(len(shown) - 1, 0)])
                self.assertLess(len(shown), len(ref) + (fail == len(p) - 1))
        self.assertEqual(self.run_pages(p, fail=len(p) + 1)[-1][0], 0)

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
