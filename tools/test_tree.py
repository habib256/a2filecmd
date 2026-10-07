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
/* A directory read as a file: its key block, one block long. */
static FILE* open_dir(const char* path, const char* mode) {
    unsigned char blk[512]; long b; FILE* f;
    if (strcmp(mode, "rb")) abort();
    if (!strcmp(path, "/V")) b = 2; else if (!strcmp(path, "/V/D")) b = 9; else return NULL;
    if (fseek(disk, b * 512, SEEK_SET) || fread(blk, 1, 512, disk) != 512) abort();
    f = tmpfile(); fwrite(blk, 1, 512, f); rewind(f); return f;
}
static char key(void) { return 13; }
static void quiet(const char* s) { (void)s; }
static void quiet_c(char c) { (void)c; }
static void at(unsigned char x, unsigned char y) { (void)x; (void)y; }
static void nothing(void) {}
static char screen[4096];
static int keep(const char* f, ...) {
    va_list ap; va_start(ap, f);
    vsnprintf(screen + strlen(screen), sizeof screen - strlen(screen), f, ap);
    strcat(screen, "\n"); va_end(ap); return 0;
}
int main(int argc, char** argv) {
    static struct A2fcApi api; static struct Panel panels[2]; static struct Entry selected;
    static unsigned char active, scratch[512]; static char note[128], full[PATH_LEN];
    disk = fopen(argv[1], "rb"); if (!disk) return 2;
    strcpy(panels[0].path, "/V");
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

    def run_tree(self, d):
        path = self.work/'v.po'
        path.write_bytes(d)
        out = subprocess.check_output([str(self.exe), str(path)], timeout=10).decode()
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
        self.assertIn('F  512 bytes (forked)', screen)

    def test_forked_file_inside_a_subdirectory(self):
        d = fixture(entries=[named(entry(13, 9, 1, 512), b'D')])
        subdir(d, 9, [named(entry(5, 6, 3, 512), b'F'), named(entry(1, 7, 1, 3), b'G')])
        note, screen = self.run_tree(d)
        self.assertEqual(note, 'TREE: 2 files, 515 bytes (directory totals include descendants).')
        self.assertIn('/V/D/ : 515 bytes, 2 files', screen)

    def test_unknown_storage_is_still_incomplete(self):
        """Storage 4 (a Pascal area) is not known to be a file."""
        note, _ = self.run_tree(fixture(entries=[named(entry(1, 4, 1, 10), b'A'),
                                                 named(entry(4, 6, 3, 512), b'P')]))
        self.assertEqual(note, 'TREE incomplete: some directories could not be scanned.')

    def test_unreadable_subdirectory_is_incomplete(self):
        d = fixture(entries=[named(entry(13, 9, 1, 512), b'E')])  # /V/E: no info
        note, _ = self.run_tree(d)
        self.assertEqual(note, 'TREE incomplete: some directories could not be scanned.')


if __name__ == '__main__':
    unittest.main()
