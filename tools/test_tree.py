"""Run TREE's actual C (src/plugins/tree.c) over a host ProDOS volume: what
it counts as a file, what makes the result INCOMPLETE, and the totals in
its last note. The volume is only read (any MLI call but GET_FILE_INFO
aborts)."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_volinfo import fixture, entry, word

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''#define __fastcall__
#define PLUGIN_HOST
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
#include "src/plugins/tree.c"
static FILE* disk;
/* GET_FILE_INFO: /V is the volume (storage $F), /V/D a subdirectory whose
 * key block is 9. Nothing else is asked; any other call is a failure. */
static unsigned char mli(unsigned char cmd, void* p) {
    struct Info* i = p;
    if (cmd != 0xC4) abort();
    if (i->path[0] == 2 && !memcmp(i->path + 1, "/V", 2)) { i->storage = 15; i->blocks = 20; return 0; }
    if (i->path[0] == 4 && !memcmp(i->path + 1, "/V/D", 4)) { i->storage = 13; i->blocks = 1; return 0; }
    return 0x46;
}
/* A directory read as a file, as ProDOS gives it: its blocks in the
 * order of their forward links, from the key block. */
static FILE* open_dir(const char* path, const char* mode) {
    unsigned char blk[512]; long b; int n = 0; FILE* f;
    if (strcmp(mode, "rb")) abort();
    if (!strcmp(path, "/V")) b = 2; else if (!strcmp(path, "/V/D")) b = 9; else return NULL;
    f = tmpfile();
    do {
        if (++n > 16 || fseek(disk, b * 512, SEEK_SET) || fread(blk, 1, 512, disk) != 512) abort();
        fwrite(blk, 1, 512, f);
        b = blk[2] | blk[3] << 8;
    } while (b);
    rewind(f); return f;
}
static char key(void) { return 13; }
static void nothing(void) {}
/* What is written to the screen, a new line at each gotoxy: one line of
 * the tree per line of the capture. */
static char screen[8192];
static void quiet(const char* s) { strncat(screen, s, sizeof screen - strlen(screen) - 1); }
static void quiet_c(char c) { char s[2] = {c, 0}; quiet(s); }
static void at(unsigned char x, unsigned char y) { (void)x; (void)y; quiet("\n"); }
static int keep(const char* f, ...) {
    va_list ap; va_start(ap, f);
    vsnprintf(screen + strlen(screen), sizeof screen - strlen(screen), f, ap);
    va_end(ap); return 0;
}
int main(int argc, char** argv) {
    static struct A2fcApi api; static struct Panel panels[2]; static struct Entry selected;
    static unsigned char active, scratch[512]; static char note[128], full[PATH_LEN];
    disk = fopen(argv[1], "rb"); if (!disk) return 2;
    strcpy(panels[0].path, argc > 2 ? argv[2] : "/V");
    api.panels = panels; api.active = &active; api.selected = &selected; api.note = note;
    api.copy_buf = scratch; api.full = full;
    api.mli = mli; api.fopen = open_dir; api.fread = fread; api.fseek = fseek; api.fclose = fclose;
    api.memcpy = memcpy; api.strcpy = strcpy; api.strlen = strlen; api.strcmp = strcmp;
    api.sprintf = sprintf; api.cprintf = keep; api.cgetc = key; api.cputs = quiet;
    api.cputc = quiet_c; api.gotoxy = at; api.clrscr = nothing;
    plugin_entry(&api);
    printf("%s\n%s", note, screen); fclose(disk); return 0;
}
'''.replace('#include <stdio.h>', '#include <stdio.h>\n#include <stdarg.h>', 1)


def named(e, name):
    e[0] = (e[0] & 0xF0) | len(name)
    e[1:1+len(name)] = name
    return e


def subdir(d, key, entries):
    """A one-block subdirectory D at `key`, holding `entries`."""
    b = key * 512
    d[b+4] = 0xE1; d[b+5] = ord('D')
    d[b+35:b+37] = bytes([39, 13])
    word(d, b+37, len(entries))
    for i, e in enumerate(entries):
        d[b+4+39*(i+1):b+4+39*(i+2)] = e


class Tree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='tree-test-')
        cls.work = Path(cls.tmp.name)
        (cls.work/'tree.c').write_text(HARNESS)
        cls.exe = cls.work/'tree'
        subprocess.run(['cc', '-std=c99', '-w', '-I', str(ROOT), str(cls.work/'tree.c'),
                        '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tree(self, d, start='/V'):
        path = self.work/'v.po'
        path.write_bytes(d)
        out = subprocess.check_output([str(self.exe), str(path), start], timeout=10).decode()
        self.assertEqual(path.read_bytes(), d, 'TREE must never write')
        note, _, screen = out.partition('\n')
        return note, screen

    def test_plain_files_are_counted(self):
        note, screen = self.run_tree(fixture(entries=[named(entry(1, 4, 1, 10), b'A'),
                                                      named(entry(2, 5, 2, 600), b'B')]))
        self.assertEqual(note, 'TREE: 2 files, 610 bytes (directory totals include descendants).')

    def test_forked_file_is_a_file(self):
        """Before: storage 5 (a GS/OS forked file) was taken for an
        unreadable directory and every GS/OS volume ended "TREE incomplete".
        Now it is a file, sized as its entry says, and the line says forked."""
        note, screen = self.run_tree(fixture(entries=[named(entry(1, 4, 1, 10), b'A'),
                                                      named(entry(5, 6, 3, 512), b'F')]))
        self.assertEqual(note, 'TREE: 2 files, 522 bytes (directory totals include descendants).')
        self.assertIn('\nF               $00 512 bytes (forked)\n', screen)

    def test_forked_file_inside_a_subdirectory(self):
        d = fixture(entries=[named(entry(13, 9, 1, 512), b'D')])
        subdir(d, 9, [named(entry(5, 6, 3, 512), b'F'), named(entry(1, 7, 1, 3), b'G')])
        note, screen = self.run_tree(d)
        self.assertEqual(note, 'TREE: 2 files, 515 bytes (directory totals include descendants).')
        self.assertIn('\nD/\n  F               $00 512 bytes (forked)\n'
                      '  G               $00 3 bytes\n  = D/ : 515 bytes, 2 files\n', screen)

    def test_unknown_storage_is_still_incomplete(self):
        """Storage 4 (a Pascal area) is not known to be a file."""
        note, _ = self.run_tree(fixture(entries=[named(entry(1, 4, 1, 10), b'A'),
                                                 named(entry(4, 6, 3, 512), b'P')]))
        self.assertEqual(note, 'TREE incomplete: some directories could not be scanned.')

    def test_unreadable_subdirectory_is_incomplete(self):
        d = fixture(entries=[named(entry(13, 9, 1, 512), b'E')])  # /V/E: no info
        note, _ = self.run_tree(d)
        self.assertEqual(note, 'TREE incomplete: some directories could not be scanned.')

    def test_tree_lines_in_disk_order(self):
        """A tree as Cat Doctor draws it: each directory by its name, its
        entries indented under it in disk order, then its totals."""
        d = fixture(entries=[named(typed(entry(1, 4, 1, 10), 0xFC), b'Z'),
                             named(entry(13, 9, 1, 512), b'D'),
                             named(typed(entry(1, 5, 1, 20), 0x06), b'A')])
        subdir(d, 9, [named(typed(entry(1, 7, 1, 3), 0x04), b'NOTE')])
        note, screen = self.run_tree(d)
        self.assertEqual(note, 'TREE: 3 files, 33 bytes (directory totals include descendants).')
        self.assertIn('TREE - READ ONLY, DISK ORDER\r\n/V\r\n\n'
                      'Z               BAS 10 bytes\n'
                      'D/\n'
                      '  NOTE            TXT 3 bytes\n'
                      '  = D/ : 3 bytes, 1 files\n'
                      'A               BIN 20 bytes\n'
                      '/V/ : 33 bytes, 3 files\n', screen)

    def test_first_system_file_of_the_volume_is_marked(self):
        """ProDOS 8 starts the first $FF file whose name ends in .SYSTEM:
        a SYS not named so, or a .SYSTEM of another type, is passed over;
        the second .SYSTEM is not the one that boots."""
        note, screen = self.run_tree(fixture(entries=[
            named(typed(entry(1, 4, 1, 10), 0xFF), b'PRODOS'),
            named(typed(entry(1, 5, 1, 10), 0x06), b'X.SYSTEM'),
            named(typed(entry(1, 6, 1, 10), 0xFF), b'BASIC.SYSTEM'),
            named(typed(entry(1, 7, 1, 10), 0xFF), b'A2FILE.SYSTEM')]))
        self.assertIn('\nPRODOS          SYS 10 bytes\n', screen)
        self.assertIn('\nX.SYSTEM        BIN 10 bytes\n', screen)
        self.assertIn('\nBASIC.SYSTEM    SYS 10 bytes  <- boots\n', screen)
        self.assertIn('\nA2FILE.SYSTEM   SYS 10 bytes\n', screen)
        self.assertEqual(screen.count('<- boots'), 1)

    def test_no_boot_mark_inside_a_subdirectory(self):
        """Only the volume directory is searched at boot: not a .SYSTEM in
        a subdirectory of it, nor one when TREE starts in a subdirectory."""
        d = fixture(entries=[named(entry(13, 9, 1, 512), b'D')])
        subdir(d, 9, [named(typed(entry(1, 7, 1, 3), 0xFF), b'B.SYSTEM')])
        for start in ('/V', '/V/D'):
            with self.subTest(start=start):
                note, screen = self.run_tree(d, start)
                self.assertIn('B.SYSTEM', screen)
                self.assertNotIn('<- boots', screen)

    def test_no_boot_guess_after_an_unknown_entry(self):
        """A forked or unknown entry before the first SYS .SYSTEM: what
        ProDOS 8 would do with it is not known, so nothing is marked."""
        for kind in (4, 5):
            with self.subTest(storage=kind):
                note, screen = self.run_tree(fixture(entries=[
                    named(typed(entry(kind, 4, 1, 10), 0xFF), b'F.SYSTEM'),
                    named(typed(entry(1, 6, 1, 10), 0xFF), b'BASIC.SYSTEM')]))
                self.assertNotIn('<- boots', screen)


    def test_boot_mark_in_a_later_root_block(self):
        """A volume directory of several blocks, as ProDOS volumes have: the
        boot mark goes to the first SYS .SYSTEM in disk order, across blocks."""
        d = fixture(entries=[named(typed(entry(1, 4+i, 1, 10), 0x06), b'F%02d' % i) for i in range(12)])
        word(d, 1024+2, 20)                     # block 2 -> block 20 (3 is the bitmap)
        word(d, 20*512, 2)
        later = [named(typed(entry(1, 30, 1, 10), 0xFF), b'LATER.SYSTEM'),
                 named(typed(entry(1, 31, 1, 10), 0xFF), b'BASIC.SYSTEM')]
        for i, e in enumerate(later):
            d[20*512+4+39*i:20*512+4+39*(i+1)] = e
        word(d, 1024+0x25, 14)
        note, screen = self.run_tree(d)
        self.assertEqual(note, 'TREE: 14 files, 140 bytes (directory totals include descendants).')
        self.assertIn('\nLATER.SYSTEM    SYS 10 bytes  <- boots\n', screen)
        self.assertIn('\nBASIC.SYSTEM    SYS 10 bytes\n', screen)
        self.assertLess(screen.index('F11 '), screen.index('LATER.SYSTEM'))

def typed(e, filetype):
    e[16] = filetype
    return e


if __name__ == '__main__':
    unittest.main()
