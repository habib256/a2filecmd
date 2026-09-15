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
#include "src/plugins/mdview.c"
static FILE* host;
static unsigned char hx, hy, bad;
static char screen[24][81];
static size_t rd_(void* p, size_t z, size_t n, FILE* f) { return fread(p, z, n, host); }
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
    struct Start st;
    int page, r;
    host = fopen(argv[1], "rb");
    fseek(host, 0, SEEK_END); sel.size = ftell(host); rewind(host);
    a.fread = rd_; a.fseek = seek__; a.gotoxy = xy_; a.cputs = puts__; a.revers = rev_;
    a.memset = memset; a.memcpy = memcpy; a.selected = &sel;
    vf = host; vbase = 0; vlen = vpos = 0;
    st.off = sniff(); st.skip = 0; st.fence = 0;
    for (page = 0; page < 200; ++page) {
        memset(screen, 0, sizeof screen); bad = 0;
        render_page(&st);
        printf("PAGE %d %u %u\n", page, done, bad);
        for (r = ROW1; r <= LASTROW; ++r) printf("|%s\n", screen[r]);
        if (done) break;
        st = next;
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

    def pages(self, data):
        f = self.p / 'in.txt'
        f.write_bytes(data)
        out = subprocess.check_output([str(self.exe), str(f)], text=True, timeout=10)
        pages = []
        for line in out.splitlines():
            if line.startswith('PAGE '):
                _, _, done, bad = line.split()
                pages.append({'done': int(done), 'bad': int(bad), 'rows': []})
            else:
                pages[-1]['rows'].append(line[1:])
        return pages

    def words(self, pages):
        return ' '.join(' '.join(p['rows']) for p in pages).split()

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
