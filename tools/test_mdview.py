"""Page MDVIEW's actual renderer over host files: no text may fall off a page.

The screen is modelled as rows 0-23; the renderer may write rows 1-21 only,
row 22 being the status line that plugin_entry prints over whatever is
there. Every word of a plain text must show up, in order, on exactly one
page, whatever row a wrapped line ends on.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
static long host_fail = -1;                 /* a read error from this offset on */
static long host_once = -1;                 /* this read call fails, once */
static int host_err, host_reads;
#define ferror(f) (host_err)
#define clear_err(f) (host_err = 0)
#include "src/plugins/mdview.c"
static FILE* host;
static unsigned char hx, hy, bad;
static char screen[24][81];
static size_t rd_(void* p, size_t z, size_t n, FILE* f)
{
    long at = ftell(host);
    if (host_err) return 0;                 /* cc65's fread, once _FERROR is set */
    if (++host_reads == host_once) { host_err = 1; return 0; }
    if (host_fail >= 0 && at + (long)n > host_fail) {
        if (at >= host_fail) { host_err = 1; return 0; }
        n = host_fail - at;               /* what comes before the bad block */
    }
    return fread(p, z, n, host);
}
static int seek__(FILE* f, long off, int whence) { return fseek(host, off, whence); }
static void xy_(unsigned char x, unsigned char y) { hx = x; hy = y; }
static void puts__(const char* s)
{
    if (hy < ROW1 || hy > LASTROW) bad = 1;     /* off the text area: never seen */
    while (*s) { if (hy < 24 && hx < 80) screen[hy][hx] = *s; ++hx; ++s; }
}
static unsigned char rev_(unsigned char r) { return 0; }
int main(int argc, char** argv)
{
    static struct Entry sel;
    struct Start st, first;
    int page, r, pass;
    host = fopen(argv[1], "rb");
    fseek(host, 0, SEEK_END); sel.size = ftell(host); rewind(host);
    a.fread = rd_; a.fseek = seek__; a.gotoxy = xy_; a.cputs = puts__; a.revers = rev_;
    a.memset = memset; a.memcpy = memcpy; a.selected = &sel;
    a.strlen = strlen; a.strcmp = strcmp;
    if (argc > 2) strcpy(sel.name, argv[2]);
    if (argc > 3) host_fail = atol(argv[3]);
    if (argc > 4) host_once = atol(argv[4]);
    vf = host; vbase = 0; vlen = vpos = 0;
    first.off = sniff(); first.skip = 0; first.fence = 0;
    /* with a failing read: after the page it hit, R -- page 1 again */
    for (pass = 0; pass < (host_once >= 0 ? 2 : 1); ++pass) {
        if (pass) printf("AGAIN\n");
        st = first;
        for (page = 0; page < 200; ++page) {
            memset(screen, 0, sizeof screen); bad = 0;
            render_page(&st);
            printf("PAGE %d %u %u\n", page, done, bad);
            for (r = ROW1; r <= LASTROW; ++r) printf("|%s\n", screen[r]);
            if (done) break;
            st = next;
        }
    }
    return 0;
}
"""


class Mdview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='mdview-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pages(self, data, name='', fail=None, once=None):
        f = self.p / 'in.txt'
        f.write_bytes(data)
        args = [name or '-'] + ([str(fail)] if fail is not None else []) if name or fail is not None else []
        if once is not None:
            args = [name or '-', '-1', str(once)]
        out = subprocess.check_output([str(self.exe), str(f)] + args, text=True, timeout=10)
        pages = []
        for line in out.splitlines():
            if line == 'AGAIN':
                self.first_pass, pages = pages, []
            elif line.startswith('PAGE '):
                _, _, done, bad = line.split()
                pages.append({'done': int(done), 'bad': int(bad), 'rows': []})
            else:
                pages[-1]['rows'].append(line[1:])
        return pages

    def words(self, pages):
        return ' '.join(' '.join(p['rows']) for p in pages).split()

    def test_a_read_error_is_not_the_end(self):
        """A block that cannot be read: the page stops there, done = 2.

        Before: getc_ took fread's 0 for the end of the file without
        ferror(), so the page said "(end)" as if the text were whole."""
        text = ''.join('line %d of the text, long enough to fill rows\n' % i for i in range(300)).encode()
        whole = self.pages(text)
        self.assertEqual([p['done'] for p in whole], [0] * (len(whole) - 1) + [1])
        for fail in (0, 700, 2048, 2049, 5000, len(text) - 20):
            with self.subTest(fail=fail):
                pages = self.pages(text, fail=fail)
                self.assertEqual(pages[-1]['done'], 2, 'the error is reported')
                self.assertTrue(all(p['done'] == 0 for p in pages[:-1]), 'only on the page it hit')
                self.assertFalse([p for p in pages if p['bad']])
                shown = self.words(pages)
                ref = self.words(whole)[:len(shown)]
                if shown:
                    self.assertEqual(shown[:-1], ref[:-1], 'what was read is right')
                    self.assertTrue(ref[-1].startswith(shown[-1]))
                self.assertLess(len(shown), len(self.words(whole)))
        # the end of the file itself is still the end
        self.assertEqual(self.pages(text, fail=len(text) + 1)[-1]['done'], 1)

    def test_r_after_a_read_error_reads_again(self):
        """One read fails, once: its page says "(read error)", then R shows
        every page again.

        Before: cc65's fread refuses every read once _FERROR is set and
        fseek clears only _FEOF/_FPUSHBACK, so R (and Up) drew empty
        pages with "(read error)" until the viewer was left."""
        text = ''.join('line %d of the text, long enough to fill rows\n' % i for i in range(300)).encode()
        whole = self.pages(text)
        for once in (2, 3, 5):              # read 1 is sniff's; each read is 2 KB
            with self.subTest(once=once):
                again = self.pages(text, once=once)
                self.assertEqual(self.first_pass[-1]['done'], 2, 'the page it hit says so')
                self.assertTrue(all(p['done'] == 0 for p in self.first_pass[:-1]))
                self.assertLess(len(self.words(self.first_pass)), len(self.words(whole)))
                self.assertEqual([(p['done'], p['rows']) for p in again],
                                 [(p['done'], p['rows']) for p in whole])

    def test_a_magic_window_document_skips_its_header(self):
        text = 'Dear reader,\rthis is a Magic Window letter.\r'
        body = bytes(c | 0x80 for c in text.encode())
        head = bytes([0x8D, 0x00]) + bytes(c | 0x80 for c in b'HEADER TEXT'.ljust(64)) + bytes(190)
        for name, words in (('LETTER.MW', text.split()), ('LETTER', None)):
            pages = self.pages(head + body, name)
            got = self.words(pages)
            if words:
                self.assertEqual(got, words)
            else:                       # another name: the header is read as text
                self.assertNotEqual(got[:2], text.split()[:2])

    def test_a_wrap_that_fills_the_page_on_the_last_character_of_a_line(self):
        """Row 21 is filled by a wrap whose carried word is the end of its
        line: that word belongs to the next page, not to the status line."""
        tail = 'b' * 9
        text = ''.join('line %02d\n' % i for i in range(20)) + 'a' * 70 + ' ' + tail + '\nafter\n'
        pages = self.pages(text.encode())
        self.assertFalse([p for p in pages if p['bad']], 'a row was drawn outside rows 1-21')
        self.assertEqual(self.words(pages), text.split())
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[1]['rows'][0], tail)
        self.assertEqual(pages[1]['rows'][1], 'after')
        self.assertTrue(pages[1]['done'])

    def test_the_carried_word_at_the_end_of_the_file(self):
        """The same wrap on the file's last line, with no line end after it."""
        text = ''.join('l%02d\n' % i for i in range(20)) + 'c' * 70 + ' ' + 'd' * 9
        pages = self.pages(text.encode())
        self.assertFalse([p for p in pages if p['bad']])
        self.assertEqual(self.words(pages), text.split())
        self.assertEqual(pages[-1]['rows'][0], 'd' * 9)
        self.assertTrue(pages[-1]['done'])

    def test_a_wrap_at_a_space_ending_the_page_leaves_no_empty_page(self):
        """A wrap on a space carries nothing: the page after must not be a
        blank replay of that line."""
        text = ''.join('l%02d\n' % i for i in range(20)) + 'e' * 79 + ' \n'
        pages = self.pages(text.encode())
        self.assertFalse([p for p in pages if p['bad']])
        self.assertEqual(self.words(pages), text.split())
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0]['done'])

    def test_every_word_of_long_wrapped_paragraphs_at_every_offset(self):
        """Paragraphs of varied word lengths, shifted row by row, so that the
        page boundary meets every kind of wrap at least once."""
        words = ('alpha be gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi '
                 'omicron pi rho sigma tau upsilon phi chi psi omega').split()
        for lead in range(0, 22):
            for extra in range(0, 12):
                para = ' '.join(words[(i * 7 + extra) % len(words)] + 'x' * ((i + extra) % 5)
                                for i in range(40 + extra))
                text = ''.join('h%02d\n' % i for i in range(lead)) + para + '\n' + para + '\nend\n'
                with self.subTest(lead=lead, extra=extra):
                    pages = self.pages(text.encode())
                    self.assertFalse([p for p in pages if p['bad']])
                    self.assertEqual(self.words(pages), text.split())


if __name__ == '__main__':
    unittest.main(verbosity=2)
