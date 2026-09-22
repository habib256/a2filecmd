"""SCIIBIN's real entry point on the host, against tools/binscii_ref.py.

The overlay (src/plugins/sciibin.c) runs with the host's files behind its
service table; the directory it walks for later parts is the order given
on the command line. Every decoded file is compared with the reference --
name, type, bytes, note -- and every refusal or failure must leave the
destination as it was. The table CRC of src/plugins/sciibin.s runs under
sim65 on both processors against the reference's bitwise one. Real
BinSCII posts from CiderPress II's test data are decoded when at hand.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import binscii_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
#include "src/plugins/sciibin.c"
static int fault, writes, argn;
static char** args;
static struct DirEntry dirent;
static int dir_i;
static unsigned char mli_(unsigned char cmd, void* params)
{
    char p[80];
    FILE* f;
    unsigned char* pas = create.path;
    if (cmd != 0xC0) abort();
    memcpy(p, pas + 1, pas[0]); p[pas[0]] = 0;
    f = fopen(p, "wx");
    if (!f) return 0x47;
    fclose(f);
    printf("CREATE %s %02X %04X\n", strrchr(p, '/') + 1, create.type, create.aux);
    return 0;
}
static FILE* writing;
static FILE* open_(const char* p, const char* m)
{
    FILE* f = fopen(p, m);
    if (!strcmp(m, "wb")) writing = f;
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    if ((fault == 1 || fault == 4) && ++writes == 3) return n - 1;
    if (fault == 2 && ++writes == 3) { unsigned char c[64]; memcpy(c, p, n); c[0] ^= 1; return fwrite(c, s, n, f); }
    return fwrite(p, s, n, f);
}
static int close_(FILE* f)
{
    if (fault == 3 && f == writing) fputc('!', f);
    return fclose(f);
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 4 ? -1 : remove(p); }
static size_t read_(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int seek_(FILE* f, long o, int w) { return fseek(f, o, w); }
static unsigned long bars, overflows;
static void bar_(const char* n, unsigned long d, unsigned long t) { ++bars; if (d > t || !*n) ++overflows; }
static unsigned char dopen_(const char* p) { dir_i = 5; return 1; }
static unsigned char dnext_(void)
{
    if (dir_i >= argn) return 0;
    strcpy(dirent.name, args[dir_i++]);
    dirent.type = 4;
    return 1;
}
static void dclose_(void) { }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    args = argv; argn = argc;
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = 4;
    fault = atoi(argv[4]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy; api.dir_entry = &dirent;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.strcmp = strcmp; api.sprintf = sprintf; api.fopen = open_; api.fread = read_;
    api.fwrite = write_; api.fseek = seek_; api.fclose = close_; api.remove = remove_;
    api.mli = mli_; api.dir_open = dopen_; api.dir_next = dnext_; api.dir_close = dclose_;
    api.progress_bar = bar_;
    plugin_entry(&api);
    printf("BARS %lu %lu\n", bars, overflows);
    printf("NOTE %s\n", note);
    return 0;
}
'''

SIM = r'''
#include <fcntl.h>
#include <unistd.h>
void bs_init(void);
void __fastcall__ bs_crc(const unsigned char* p);
extern unsigned int bs_sum;
static unsigned char line[48];
int main(void)
{
    int in = open("data.bin", O_RDONLY);
    bs_init();
    bs_sum = 0;
    while (read(in, line, 48) == 48) bs_crc(line);
    write(1, &bs_sum, 2);
    return 0;
}
'''


class Sciibin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sciibin-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-D_POSIX_C_SOURCE=0', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_sb(self, files, selected, fault=0, existing=()):
        """files: [(name, bytes)] in directory order; the ones after `selected` are its successors."""
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        for n, data in files:
            (case / 'S' / n).write_bytes(data)
        for e in existing:
            (case / 'D' / e).write_bytes(b'old')
        names = [n for n, _ in files]
        out = subprocess.run([str(self.exe), str(case / 'S'), str(case / 'D'), selected,
                              str(fault)] + names, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        self.bars = [int(v) for l in lines if l.startswith('BARS ') for v in l.split()[1:]]
        made = {p.name: p.read_bytes() for p in (case / 'D').iterdir()}
        return note, created, removed, made

    def check(self, files, selected):
        names = [n for n, _ in files]
        texts = [d for n, d in files[names.index(selected):]]
        note, created, removed, made = self.run_sb(files, selected)
        try:
            name, access, t, a, data = ref.decode(texts)
        except ref.Bad as e:
            self.assertEqual(made, {}, (str(e), note))
            return note
        self.assertEqual(created, [[name, '%02X' % t, '%04X' % a]], note)
        self.assertEqual(made, {name: data})
        self.assertEqual(note, '%s: %d bytes, $%02X/$%04X, %d chunks.' % (
            name, len(data), t, a, (len(data) + ref.SEGMENT - 1) // ref.SEGMENT))
        return note

    def split(self, text):
        parts = text.split(b'FiLeStArTfIlEsTaRt')
        head = parts[0] + b'FiLeStArTfIlEsTaRt' + parts[1]
        return [head] + [b'FiLeStArTfIlEsTaRt' + p for p in parts[2:]]

    def test_single_and_multi_part(self):
        rng = random.Random(2)
        for size in (1, 48, 12288, 12289, 40000):
            data = bytes(rng.randrange(256) for _ in range(size))
            text = ref.encode('PROG.NAME', data, ftype=0xFF, aux=0x2000,
                              eol=rng.choice([b'\r', b'\n', b'\r\n']))
            with self.subTest(size=size):
                self.check([('P.BSC', text), ('OTHER', b'hello')], 'P.BSC')
                if size > ref.SEGMENT:
                    parts = self.split(text)
                    files = [('P.%02d' % i, p) for i, p in enumerate(parts)] + [('LAST', b'x')]
                    self.check(files, 'P.00')
                    # a missing part, parts out of order, an unrelated file between
                    note = self.check([files[0]] + files[2:], 'P.00')
                    self.assertTrue(note.endswith('removed.'), note)
                    note = self.check([files[1], files[0]] + files[2:], 'P.01')
                    self.assertTrue(note.startswith('Parts out of order') or note.endswith('removed.'), note)
                    note = self.check([files[0], ('NOTE', b'text'), *files[1:]], 'P.00')
                    self.assertEqual(note, 'Parts missing: PROG.NAME removed.')

    def test_progress(self):
        # About 15 ms a line at 1 MHz: a 40,000-byte file is 834 lines to
        # decode and 834 to read back, the bar moving every 16 of them.
        data = bytes(range(256)) * 157
        self.check([('P.BSC', ref.encode('BIG', data))], 'P.BSC')
        lines = (len(data) + 47) // 48
        self.assertGreaterEqual(self.bars[0], 2 * (lines // 16) - 2)
        self.assertEqual(self.bars[1], 0)

    def test_damage_is_refused(self):
        text = ref.encode('DOC', bytes(range(256)) * 10)
        lines = text.split(b'\r')
        for k, pos, what in ((2, 10, 'alphabet'), (3, 20, 'header'), (4, 10, 'data line'),
                             (-3, 1, 'crc line')):
            bad = list(lines)
            i = k if k > 0 else len(bad) + k
            j = pos
            bad[i] = bad[i][:j] + (b'!' if bad[i][j:j + 1] != b'!' else b'#') + bad[i][j + 1:]
            with self.subTest(what):
                note = self.check([('D.BSC', b'\r'.join(bad))], 'D.BSC')
                self.assertIn(note, ('BinSCII damaged', 'BinSCII damaged: DOC removed.'))
        # a character swapped for another of the alphabet: only the CRCs see it
        for k, pos, what in ((3, 20, 'header'), (4, 10, 'data line'), (2, 5, 'alphabet twice')):
            bad = list(lines)
            c = bad[k][pos:pos + 1]
            bad[k] = bad[k][:pos] + (b'A' if c != b'A' else b'B') + bad[k][pos + 1:]
            with self.subTest(what):
                note = self.check([('D.BSC', b'\r'.join(bad))], 'D.BSC')
                self.assertIn(note, ('BinSCII damaged', 'BinSCII damaged: DOC removed.'))
        blanks = text.replace(b'FiLeStArTfIlEsTaRt', b'  FiLeStArTfIlEsTaRt \t')
        self.assertEqual(self.check([('B.BSC', blanks)], 'B.BSC'), 'DOC: 2560 bytes, $06/$0000, 1 chunks.')
        self.assertEqual(self.check([('N.TXT', b'just text\r')], 'N.TXT'), 'Not BinSCII text')

    def test_failures_remove_the_output(self):
        text = ref.encode('DOC', bytes(range(256)) * 10)
        for fault in (1, 2, 3):
            with self.subTest(fault=fault):
                note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', fault)
                self.assertEqual((removed, made), (['DOC'], {}), note)
                self.assertTrue(note.endswith('DOC removed.'), note)
        note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', 4)
        self.assertEqual((note, list(made)), ('Cleanup failed: the incomplete file stays.', ['DOC']))
        note, created, removed, made = self.run_sb([('D.BSC', text)], 'D.BSC', existing=['DOC'])
        self.assertEqual((note, made), ('DOC exists or cannot be created.', {'DOC': b'old'}))

    def test_real_posts(self):
        v = cp2_samples.volume()
        self.check([('SHRINKIT.BSC', v['/ARCHIVES/SHRINKIT.BSC'][2])], 'SHRINKIT.BSC')
        files = [('ZLINK.%02d.BSQ' % i, v['/ARCHIVES/ZLINK.%02d.BSQ' % i][2]) for i in range(1, 6)]
        note = self.check(files, 'ZLINK.01.BSQ')
        self.assertEqual(note, 'Z.LINK.SHK: 54568 bytes, $E0/$8002, 5 chunks.')

    def test_table_crc_under_sim65(self):
        rng = random.Random(3)
        data = bytes(rng.randrange(256) for _ in range(48 * 300))
        (self.root / 'data.bin').write_bytes(data)
        shutil.copyfile(ROOT / 'src/plugins/sciibin.s', self.root / 'sciibin.s')
        (self.root / 'sim.c').write_text(SIM)
        for cpu in ('sim6502', 'sim65c02'):
            exe = self.root / cpu
            subprocess.run(['cl65', '-t', cpu, '-O', '-o', str(exe), str(self.root / 'sim.c'),
                            str(self.root / 'sciibin.s')], check=True, cwd=self.root,
                           capture_output=True)
            out = subprocess.run(['sim65', str(exe)], cwd=self.root, capture_output=True, timeout=60)
            self.assertEqual(int.from_bytes(out.stdout, 'little'), ref.crc16(data), cpu)


if __name__ == '__main__':
    unittest.main()
