#!/usr/bin/env python3
"""The text viewer says when it could not read on, and when it cannot page on.

The real view_text and view_getc of src/a2fc.c, on the host. Measured
before the fix (0.9.5): a read error in the middle of a file showed
"page 2 (end)" -- an I/O error taken for the end of the file, which
AGENTS.md forbids -- and a file longer than the 80 page starts the viewer
remembers stopped at "page 80" with nothing said, Space doing nothing and
the rest out of reach. BASLIST and the AppleWorks reader carry the same two
lines of code.

    python3 tools/test_text_viewer.py
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()

HARNESS = r'''
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define KEY_ESC 27
#define KEY_RETURN 13
#define KEY_LEFT 8
#define KEY_RIGHT 21
#define KEY_UP 11
#define KEY_DOWN 10
static unsigned char copy_buf[512];
static long text_starts[80];
static unsigned char a2fc_view;
static const char* keys;
static long fail_at = -1, served;
static int read_failed;
static void report_error(const char* w) { printf("ERROR %s\n", w); }
static void clrscr(void) {}
static void gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static void cputc(char c) { (void)c; }
static void bar_begin(void) {}
static void keys_bar(unsigned char x, const char* k) { (void)x; (void)k; }
static void draw_all(void) {}
static void cprintf(const char* f, ...) { va_list a; va_start(a, f); vprintf(f, a); va_end(a); putchar('\n'); }
static char cgetc(void) { return *keys ? *keys++ : KEY_ESC; }
/* A device that fails at byte fail_at: the bytes before it are served, then
 * nothing and the stream's error indicator, as cc65's fread leaves it. */
static size_t read_(void* p, size_t s, size_t n, FILE* f)
{
    size_t got;
    if (fail_at >= 0 && served + (long)n > fail_at) n = fail_at > served ? fail_at - served : 0;
    got = n ? fread(p, s, n, f) : 0;
    if (fail_at >= 0 && served + (long)got >= fail_at) read_failed = 1;
    served += got;
    return got;
}
static int seek_(FILE* f, long o, int w) { served = o; return fseek(f, o, w); }
#define fread read_
#define fseek seek_
#define ferror(f) read_failed
VIEWER
int main(int argc, char** argv)
{
    keys = argv[2];
    if (argc > 3) fail_at = atol(argv[3]);
    view_text(argv[1]);
    return 0;
}
'''


def viewer():
    a = SOURCE.index('static FILE* vf;')
    b = SOURCE.index('/* S: the next sort order.', a)
    return '\n'.join(l for l in SOURCE[a:b].splitlines() if not l.startswith('#pragma'))


class TextViewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='text-viewer-')
        p = Path(cls.tmp.name)
        (p / 'v.c').write_text(HARNESS.replace('VIEWER', viewer()))
        subprocess.run(['cc', '-std=c99', '-fsanitize=address,undefined', '-o', str(p / 'v'), str(p / 'v.c')],
                       check=True, capture_output=True)
        cls.exe, cls.file = str(p / 'v'), p / 'TEXT'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pages(self, data, keys, fail_at=None):
        self.file.write_bytes(data)
        args = [self.exe, str(self.file), keys] + ([str(fail_at)] if fail_at is not None else [])
        out = subprocess.run(args, capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()
        return [l.split(' page ', 1)[1] for l in out if ' page ' in l]

    def test_a_short_file_ends(self):
        self.assertEqual(self.pages(b'ONE\rTWO\rTHREE\r', ''), ['1 (end)'])

    def test_pages_forward_and_back(self):
        data = b''.join(b'LINE %03d\r' % i for i in range(50))          # 22 rows a page: three pages
        self.assertEqual(self.pages(data, '  B R'), ['1', '2', '3 (end)', '2', '3 (end)', '1'])

    def test_a_read_error_is_not_the_end(self):
        data = b''.join(b'LINE %03d\r' % i for i in range(200))         # 1,800 bytes
        got = self.pages(data, '    ', fail_at=600)
        self.assertEqual(got[0], '1')                                    # the first page is whole
        self.assertIn('(READ ERROR)', got[-1])
        self.assertFalse(any('(end)' in g for g in got), got)
        # an error in the very first block: nothing to show, and it is said
        self.assertEqual(self.pages(data, '', fail_at=0), ['1 (READ ERROR)'])

    def test_the_page_limit_is_said(self):
        data = b''.join(b'L%04d\r' % i for i in range(22 * 100))        # a hundred pages
        got = self.pages(data, ' ' * 120)
        self.assertEqual(got[78], '79')
        self.assertEqual(got[79], '80 (page limit)')
        self.assertEqual(got[-1], '80 (page limit)')                     # Space stays there
        self.assertFalse(any('(end)' in g for g in got))
        # exactly eighty pages: the end, not the limit
        data = b''.join(b'L%04d\r' % i for i in range(22 * 79 + 5))
        self.assertEqual(self.pages(data, ' ' * 90)[-1], '80 (end)')

    def test_the_two_other_readers_carry_the_same_lines(self):
        for prefix in ('bl', 'aw'):
            with self.subTest(reader=prefix):
                self.assertRegex(SOURCE, r'done \? \(ferror\(vf\) \? %s_\w+ : %s_end\) : page \+ 1 < TEXT_PAGES \? '
                                         r'\(const char\*\)"" : %s_limit' % (prefix, prefix, prefix))


if __name__ == '__main__':
    unittest.main()
