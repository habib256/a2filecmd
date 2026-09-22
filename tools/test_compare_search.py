"""Run the real COMPARE and SEARCH overlay code against host files with I/O faults.

A read, open or close error must never read as "Identical", as a shorter file,
as "No such file" or as a file without the text.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()


def section(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end, SOURCE.index(start))]


SEARCH = section('static const char srch_label[]', '#pragma static-locals (pop)')
SEARCH = SEARCH.replace('*(volatile unsigned char*)0xC000', 'keyboard').replace('*(volatile unsigned char*)0xC010', 'keyboard')

C = r'''
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __fastcall__
#include "src/a2fc_plugin.h"
static struct Panel panels[2];
static struct Entry table[2][MAX_ENTRIES], selected;
static unsigned char active, copy_buf[512], _oserror, keyboard;
static char full[PATH_LEN + NAME_LEN], other_full[PATH_LEN + NAME_LEN], input[NAME_LEN], question[64], shown[128];
static const char* fault;
static int opens, closes;
struct Open { FILE* f; char name[16]; int reads, error; };
static struct Open files[8];
static struct Open* slot(FILE* f) { int i; for (i = 0; i < 8; ++i) if (files[i].f == f) return &files[i]; abort(); }
static int faulty(const char* name, const char* what) {
    char key[40]; sprintf(key, "%s:%s", what, name); return strstr(fault, key) != NULL;
}
static FILE* open_file(const char* p, const char* mode) {
    const char* name = strrchr(p, '/') + 1;
    char dir = p[strlen(p) - strlen(name) - 2];      /* A or B for COMPARE */
    char tag[20]; FILE* f; int i;
    sprintf(tag, "%c%s", dir, name);
    if (strcmp(mode, "rb")) abort();
    if (faulty(tag, "open")) { _oserror = 0x50; return NULL; }
    f = fopen(p, mode);
    if (!f) { _oserror = errno == ENOENT ? 0x46 : 0x27; return NULL; }
    for (i = 0; files[i].f; ++i) ;
    files[i].f = f; strcpy(files[i].name, tag); files[i].reads = files[i].error = 0;
    ++opens; _oserror = 0;
    return f;
}
static size_t read_file(void* p, size_t s, size_t n, FILE* f) {
    struct Open* o = slot(f);
    char key[24];
    sprintf(key, "%s@%d", o->name, ++o->reads);
    if (faulty(key, "read")) { o->error = 1; _oserror = 0x27; return n > 100 ? 100 : 0; }
    _oserror = 0;
    return fread(p, s, n, f);
}
static int error_file(FILE* f) { return slot(f)->error || ferror(f); }
static int close_file(FILE* f) {
    struct Open* o = slot(f);
    int bad = faulty(o->name, "close");
    o->f = NULL; ++closes; fclose(f);
    _oserror = bad ? 0x27 : 0;       /* like cc65: a good close clears _oserror */
    return bad ? -1 : 0;
}
#define fopen open_file
#define fread read_file
#define ferror error_file
#define fclose close_file
static unsigned char is_dir(const struct Entry* e) { return e->type == 0x0F; }
static unsigned char tagged(const struct Panel* pan, unsigned char i) { return (pan->tags[i >> 3] >> (i & 7)) & 1; }
static void set_tag(struct Panel* pan, unsigned char i, unsigned char on) {
    if (on) pan->tags[i >> 3] |= 1 << (i & 7); else pan->tags[i >> 3] &= ~(1 << (i & 7));
}
static void message(const char* s) { snprintf(shown, sizeof shown, "%s", s); }
static void report_error(const char* s) { snprintf(shown, sizeof shown, "ERROR %s $%02X", s, _oserror); }
static void too_long(void) { strcpy(shown, "TOO LONG"); }
static unsigned char target_check(void) { return 1; }
static void show_active(void) {}
static void clear_row(unsigned char r) { (void)r; }
static void gotoxy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static void open_row22(void) { clear_row(22); gotoxy(0, 22); }
static void draw_panel(unsigned char p) { (void)p; }
static unsigned int progress_done, progress_total, ticks;
static void activity_tick(void) { ++ticks; }
static void progress_bar(const char* s, unsigned long d, unsigned long t) {
    fprintf(stderr, "BAR %u/%u %s %lu %lu\n", progress_done + 1, progress_total, s, d, t);
}
#define cprintf printf
static unsigned char prompt(const char* l, const char* i, unsigned char h) {
    (void)l; (void)i; (void)h; strcpy(input, "WIDGET"); return 1;
}
''' + section('static unsigned char build_full(', 'static const char read_path_error[]') \
  + section('static const char cmp_pick[]', '#pragma static-locals (pop)') + SEARCH + r'''
int main(int argc, char** argv) {
    struct A2fcApi api;
    int i;
    memset(&api, 0, sizeof api);
    fault = argv[2];
    panels[0].e = table[0]; panels[1].e = table[1];
    if (!strcmp(argv[1], "compare")) {
        /* argv: compare FAULTS /dir/A/NAME /dir/B */
        strcpy(full, argv[3]); strcpy(panels[1].path, argv[4]);
        strcpy(selected.name, strrchr(argv[3], '/') + 1); selected.type = 6;
        compare_entry(&api);
        printf("%s|%d\n", shown, opens - closes);
        fprintf(stderr, "TICKS %u\n", ticks);
    } else {
        /* argv: search FAULTS /dir NAME... */
        strcpy(panels[0].path, argv[3]);
        for (i = 4; i < argc; ++i) { strcpy(table[0][i - 4].name, argv[i]); table[0][i - 4].type = 6; }
        panels[0].count = argc - 4;
        search_entry(&api);
        printf("%s|%d|%02X\n", shown, opens - closes, panels[0].tags[0]);
    }
    return 0;
}
'''


class CompareSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='cmp-build-')
        p = Path(cls.build.name)
        (p / 'test.c').write_text(C)
        cls.exe = p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT), str(p / 'test.c'),
                        '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cmp', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'A').mkdir()
        (self.root / 'B').mkdir()

    def files(self, a, b=None):
        (self.root / 'A/F').write_bytes(a)
        if b is not None:
            (self.root / 'B/F').write_bytes(b)
        return {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def compare(self, faults='', other=None):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        run = subprocess.run([str(self.exe), 'compare', faults, str(self.root / 'A/F'),
                              other or str(self.root / 'B')], text=True, capture_output=True, check=True)
        out = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        shown, leaked = out.rsplit('|', 1)
        self.assertEqual(leaked, '0')
        return shown

    def test_results_without_faults(self):
        data = bytes(range(256)) * 2 + b'tail'
        self.files(data, data)
        self.assertEqual(self.compare(), 'Identical: 516 bytes.')
        self.files(data, data[:300] + b'X' + data[301:])
        self.assertEqual(self.compare(), 'Differ at byte 300.')
        self.files(data, data[:400])
        self.assertEqual(self.compare(), 'Same for 400 bytes, then longer.')

    def test_a_long_compare_keeps_the_activity_cell_turning(self):
        # No room for a bar in COMPARE: one tick per 256-byte read.
        data = bytes(range(256)) * 12
        self.files(data, data)
        self.assertEqual(self.compare(), 'Identical: 3072 bytes.')
        self.assertEqual(self.trace, ['TICKS 13'])

    def test_read_errors_are_not_the_end_of_a_file(self):
        data = b'z' * 600
        self.files(data, data)
        for faults in ('read:BF@2', 'read:AF@2', 'read:AF@2 read:BF@2', 'read:AF@1 read:BF@1', 'read:BF@3'):
            with self.subTest(faults=faults):
                self.assertEqual(self.compare(faults), 'Compare failed: read/close error.')

    def test_close_errors_never_confirm_identical_files(self):
        self.files(b'same', b'same')
        for faults in ('close:AF', 'close:BF', 'close:AF close:BF'):
            with self.subTest(faults=faults):
                self.assertEqual(self.compare(faults), 'Compare failed: read/close error.')

    def test_only_a_missing_file_is_no_such_file(self):
        self.files(b'same')
        self.assertEqual(self.compare(), 'No such file in the other panel.')
        self.files(b'same', b'same')
        self.assertEqual(self.compare('open:BF'), 'ERROR Open $50')

    def test_other_path_beyond_prodos_limit_is_refused_before_opening(self):
        self.files(b'same', b'same')
        self.assertEqual(self.compare(other='/' + 'L' * 62), 'TOO LONG')

    def search(self, faults, *names):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        run = subprocess.run([str(self.exe), 'search', faults, str(self.root / 'A'), *names],
                             text=True, capture_output=True, check=True)
        out = run.stdout.strip()
        self.trace = run.stderr.splitlines()
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        shown, leaked, tags = out.rsplit('|', 2)
        self.assertEqual(leaked, '0')
        return shown, int(tags, 16)

    def test_search_tags_matches(self):
        for name, text in (('HAS1', b'x' * 510 + b'wid' + b'get'), ('NONE', b'nothing'), ('HAS2', b'WIDGET')):
            (self.root / 'A' / name).write_bytes(text)
        self.assertEqual(self.search('', 'HAS1', 'NONE', 'HAS2'), ('2 file(s) contain "WIDGET", now tagged.', 0b101))

    def test_search_names_each_file_it_reads(self):
        # "n/m NAME": which file of the panel is being read, bar across the panel.
        (self.root / 'A/HAS1').write_bytes(b'a WIDGET here')
        (self.root / 'A/NONE').write_bytes(b'nothing')
        self.search('', 'HAS1', 'NONE')
        self.assertEqual([l for l in self.trace if l.startswith('BAR ')],
                         ['BAR 1/2 HAS1 0 2', 'BAR 2/2 NONE 1 2'])

    def test_search_stops_and_reports_unreadable_files(self):
        for name in ('HAS1', 'BAD', 'HAS2'):
            (self.root / 'A' / name).write_bytes(b'x' * 600 + b'WIDGET')
        for faults in ('read:ABAD@1', 'read:ABAD@2', 'open:ABAD', 'close:ABAD'):
            with self.subTest(faults=faults):
                self.assertEqual(self.search(faults, 'HAS1', 'BAD', 'HAS2'),
                                 ('Read error: BAD; 1 tagged, stopped.', 0b001))
        (self.root / 'A/BAD').unlink()
        self.assertEqual(self.search('', 'HAS1', 'BAD', 'HAS2'), ('Read error: BAD; 1 tagged, stopped.', 0b001))


if __name__ == '__main__':
    unittest.main()
