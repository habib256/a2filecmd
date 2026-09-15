"""Run DISKCMP's actual entry point against mocked ProDOS units.

Two drives may carry the same volume name -- an original and its backup in
S6,D1 and S6,D2 -- and a comparison of a volume with itself must never be
reported as "Identical".
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
#include "src/plugins/diskcmp.c"
static FILE* disks[16];
static char names[16][16];
static unsigned int reads[16];
static const char* typed;
static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Online* o = p;
    struct Block* b = p;
    unsigned int i, n;
    if (cmd == 0xC5) {
        if (o->unit) abort();                    /* only ON_LINE of every unit here */
        memset(o->buffer, 0, 256);
        for (i = 1, n = 0; i < 16; ++i) if (names[i][0]) {
            o->buffer[n] = (unsigned char)(i << 4) | (unsigned char)strlen(names[i]);
            memcpy(o->buffer + n + 1, names[i], strlen(names[i]));
            n += 16;
        }
        return 0;
    }
    if (cmd != 0x80) abort();                    /* READ_BLOCK only: a write fails the test */
    i = b->unit >> 4;
    if (!disks[i]) return 0x28;
    ++reads[i];
    if (fseek(disks[i], (long)b->block * 512, SEEK_SET)) return 0x27;
    return fread(b->buffer, 1, 512, disks[i]) == 512 ? 0 : 0x27;
}
static void message_(const char* s) {}
static char key_(void) { return 'V'; }
static unsigned char prompt_(const char* label, const char* init, unsigned char hex)
{
    strcpy(a.input, typed); return 1;
}
static void clear_(void) {}
static int cprintf_(const char* f, ...) { return 0; }
static void bar_(const char* s, unsigned long d, unsigned long t) {}
/* argv: panel path ("" = the volume list), selected name, selected unit,
 * typed name, then unit=image pairs such as 6=/tmp/a.po */
int main(int argc, char** argv)
{
    static struct Panel panels[2];
    static struct Entry sel;
    static unsigned char scratch[512], active;
    static char input[17], note_[80], full[81], other[81];
    struct A2fcApi api;
    int i;
    for (i = 5; i < argc; ++i) {
        unsigned int u = strtoul(argv[i], 0, 16);
        disks[u] = fopen(strchr(argv[i], '=') + 1, "rb");
        strcpy(names[u], "V");
    }
    strcpy(panels[0].path, argv[1]);
    strcpy(sel.name, argv[2]); sel.mdate = strtoul(argv[3], 0, 16);
    typed = argv[4];
    memset(&api, 0, sizeof api);
    api.panels = panels; api.active = &active; api.selected = &sel;
    api.copy_buf = scratch; api.input = input; api.note = note_;
    api.full = full; api.other_full = other;
    api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.sprintf = sprintf; api.message = message_; api.cgetc = key_; api.prompt = prompt_;
    api.mli = mock_mli; api.clrscr = clear_; api.cprintf = cprintf_; api.progress_bar = bar_;
    plugin_entry(&api);
    printf("%s\n", note_);
    for (i = 1; i < 16; ++i) if (disks[i]) printf("%x %u\n", i, reads[i]);
    return 0;
}
"""


def volume(blocks=280, name=b'V', mark=0):
    d = bytearray(blocks * 512)
    d[1028] = 0xF0 | len(name)
    d[1029:1029 + len(name)] = name
    d[1065:1067] = blocks.to_bytes(2, 'little')
    d[5 * 512 + 7] = mark
    return bytes(d)


class Diskcmp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='diskcmp-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_cmp(self, panel, name, unit, typed, disks):
        args = [str(self.exe), panel, name, '%x' % unit, typed]
        for u, data in disks.items():
            f = self.p / ('d%x.po' % u)
            f.write_bytes(data)
            args.append('%x=%s' % (u, f))
        out = subprocess.check_output(args, text=True, timeout=20).splitlines()
        for u, data in disks.items():
            self.assertEqual((self.p / ('d%x.po' % u)).read_bytes(), data, 'read only')
        return out[0], {int(u, 16): int(n) for u, n in (l.split() for l in out[1:])}

    def test_same_name_on_two_drives_from_inside_the_volume(self):
        """The panel shows /V (resolved to the first V); the second V must be
        the OTHER drive, whose block 5 differs."""
        note, reads = self.run_cmp('/V', 'FILE', 0, 'V', {0x6: volume(), 0xE: volume(mark=1)})
        self.assertEqual(note, '1 differing blocks; first at 5.')
        self.assertTrue(reads[0x6] and reads[0xE])

    def test_same_name_on_two_drives_from_the_volume_list(self):
        for sel, other in ((0x6, 0xE), (0xE, 0x6)):
            with self.subTest(selected=sel):
                note, reads = self.run_cmp('', '/V', sel, 'V', {0x6: volume(), 0xE: volume(mark=1)})
                self.assertEqual(note, '1 differing blocks; first at 5.')
                self.assertTrue(reads[sel] and reads[other])

    def test_identical_copies_on_two_drives(self):
        note, reads = self.run_cmp('/V', 'FILE', 0, 'V', {0x6: volume(), 0xE: volume()})
        self.assertEqual(note, 'Identical: 280 blocks compared.')
        self.assertGreaterEqual(min(reads[0x6], reads[0xE]), 280)

    def test_a_volume_is_never_compared_with_itself(self):
        for panel, name in (('/V', 'FILE'), ('', '/V')):
            with self.subTest(panel=panel):
                note, _ = self.run_cmp(panel, name, 0x6, 'V', {0x6: volume(mark=1)})
                self.assertNotIn('Identical', note)
                self.assertIn('Cannot compare', note)


if __name__ == '__main__':
    unittest.main(verbosity=2)
