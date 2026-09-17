"""UNWRAP's real entry point on the host, against tools/unwrap_ref.py.

The overlay (src/plugins/unwrap.c) runs with the ProDOS calls and the C
library of the host behind its service table. Every extraction is compared
with the reference: the name, the ProDOS type and auxiliary type given to
CREATE, the bytes written, the note. Refusals must leave the destination
directory as it was; a failed write or read-back removes what was created.
Real files from CiderPress II's test data are added when at hand.
"""
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unwrap_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
#include <errno.h>
#include <sys/stat.h>
#include "src/plugins/unwrap.c"
static int fault, writes, reads_out;
static FILE* reading_back;
static unsigned char mli_(unsigned char cmd, void* params)
{
    char p[80];
    FILE* f;
    unsigned char* pas = create.path;
    if (cmd != 0xC0) abort();
    memcpy(p, pas + 1, pas[0]); p[pas[0]] = 0;
    if (fault == 1) return 0x27;
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
    if (fault == 4 && !strcmp(m, "rb") && strstr(p, "/D/")) { if (f) fclose(f); return NULL; }
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    if ((fault == 2 || fault == 5) && ++writes == 2) return n - 1;
    if (fault == 3) { unsigned char c[512]; memcpy(c, p, n); c[n - 1] ^= 1; return fwrite(c, s, n, f); }
    return fwrite(p, s, n, f);
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 5 ? -1 : remove(p); }
static int close_(FILE* f)
{
    if (fault == 6 && f == writing) fputc('!', f);          /* one byte too many */
    return fclose(f);
}
static size_t read_(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int seek_(FILE* f, long o, int w) { return fseek(f, o, w); }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    FILE* s;
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = strtol(argv[4], 0, 16);
    fault = atoi(argv[5]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    s = fopen(full, "rb"); fseek(s, 0, SEEK_END); sel.size = ftell(s); fclose(s);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.sprintf = sprintf; api.fopen = open_; api.fread = read_; api.fwrite = write_;
    api.fseek = seek_; api.fclose = close_; api.remove = remove_; api.mli = mli_;
    plugin_entry(&api);
    printf("NOTE %s\n", note);
    return 0;
}
'''


class Unwrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unwrap-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_unwrap(self, name, data, fault=0, typ='06', existing=()):
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        (case / 'S' / name).write_bytes(data)
        for e in existing:
            (case / 'D' / e).write_bytes(b'old')
        out = subprocess.run([str(self.exe), str(case / 'S'), str(case / 'D'), name, typ,
                              str(fault)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        files = {p.name: p.read_bytes() for p in (case / 'D').iterdir()}
        self.assertEqual((case / 'S' / name).read_bytes(), data, 'the source is untouched')
        return note, created, removed, files

    def check(self, name, data, typ='06'):
        want = ref.unwrap(data, name)
        note, created, removed, files = self.run_unwrap(name, data, typ=typ)
        if want is None:
            self.assertEqual(note, 'Not an AppleSingle or MacBinary file.')
            self.assertEqual((created, files), ([], {}))
            return
        wname, t, a, fork, rsrc = want
        self.assertEqual(created, [[wname, '%02X' % t, '%04X' % a]])
        self.assertEqual(files, {wname: fork})
        self.assertEqual(note, '%s: %d bytes, $%02X/$%04X.%s' % (
            wname, len(fork), t, a, ' Resource fork left out.' if rsrc else ''))
        self.assertEqual(removed, [])

    def test_synthetic_files(self):
        rng = random.Random(1)
        types = [b'TEXTttxt', b'p\x06\x20\x00pdos', b'FC  pdos', b'PSYSpdos', b'PS16pdos',
                 b'dImgdCpy', b'AIFCxxxx', b'MIDIxxxx', b'APPLMSWD', b'Z1  pdos', b'p\x0f\x00\x00pdos']
        for i in range(60):
            fork = bytes(rng.randrange(256) for _ in range(rng.choice([0, 1, 511, 512, 513, 3000])))
            rsrc = b'r' * rng.choice([0, 5])
            raw = bytes(rng.choice(b'abcXYZ019 .-_:/\x8a') for _ in range(rng.randint(0, 40)))
            if i % 2:
                entries = [(1, fork)]
                if raw:
                    entries.insert(0, (3, raw))
                if rsrc:
                    entries.append((2, rsrc))
                k = rng.random()
                if k < 0.3:
                    entries.append((11, bytes([0, 0xC3, 0, rng.randrange(256), 0, 0,
                                                rng.randrange(256), rng.randrange(256)])))
                elif k < 0.6:
                    entries.append((9, rng.choice(types) + bytes(24)))
                rng.shuffle(entries)
                v = rng.choice([1, 2])
                data = ref.make_as(entries, version=v, home=b'ProDOS' if v == 1 else b'')
                if v == 1 and rng.random() < 0.5:
                    data = ref.make_as(entries + [(7, bytes(8) + bytes([0, 0xE3, 0, 0x2A, 0, 0, 0x12, 0x34]))],
                                       version=1, home=b'ProDOS')
                name = 'FILE%d.AS' % i
            else:
                data = ref.make_mb(raw or b'x', rng.choice(types), fork, rsrc,
                                   version=rng.choice([1, 2]))
                name = 'FILE%d.BIN' % i
            with self.subTest(i=i):
                self.check(name, data)

    def test_real_files(self):
        v = cp2_samples.volume()
        real = [v[k][2] for k in sorted(v) if k.startswith('/ARCHIVES/') and k.endswith('.AS')]
        self.assertEqual(len(real), 3, 'data/CP2/ARCHIVES holds three AppleSingle files')
        for n in ('as/badmac-utf8name.as', 'as/illegal-chars.as'):
            p = cp2_samples.path(n)
            if p:
                real.append(p.read_bytes())
        for i, data in enumerate(real):
            with self.subTest(i=i):
                self.check('SAMPLE.AS', data, typ='E0')

    def test_precedence_and_macbinary_i(self):
        prodos = (11, bytes([0, 0xC3, 0, 0x06, 0, 0, 0x20, 0x00]))
        finder = (9, b'TEXTttxt' + bytes(24))
        for order in ([prodos, finder], [finder, prodos]):
            data = ref.make_as([(3, b'P')] + order + [(1, b'x')])
            self.check('P.AS', data)
            self.assertEqual(ref.unwrap(data, 'P.AS')[1:3], (6, 0x2000))
        m = bytearray(ref.make_mb(b'Old', b'TEXTttxt', b'abc', version=1))
        m[99] = 1                       # neither a MacBinary I nor a valid CRC
        self.check('OLD.BIN', bytes(m))
        self.assertIsNone(ref.unwrap(bytes(m), 'OLD.BIN'))

    def test_refusals_and_failures(self):
        good = ref.make_as([(3, b'Doc'), (1, b'hello' * 300)])
        for data in (b'', b'\x00\x05\x16\x00' + bytes(10), b'\x00\x05\x16\x00\x00\x03' + bytes(30),
                     good[:40], good[:-1], ref.make_as([(3, b'No fork')]),
                     ref.make_mb(b'', b'TEXTttxt', b'x'),
                     ref.make_mb(b'x', b'TEXTttxt', b'x' * 200)[:200],
                     bytes(200)):
            note, created, removed, files = self.run_unwrap('BAD.AS', data)
            self.assertEqual((note, created, files), ('Not an AppleSingle or MacBinary file.', [], {}),
                             data[:12])
        note, created, removed, files = self.run_unwrap('X.AS', good, existing=['DOC'])
        self.assertEqual((note, files), ('DOC exists or cannot be created.', {'DOC': b'old'}))
        for fault in (2, 3, 4, 6):
            with self.subTest(fault=fault):
                note, created, removed, files = self.run_unwrap('X.AS', good, fault=fault)
                self.assertEqual((note, removed, files), ('Extraction failed: DOC removed.', ['DOC'], {}))
        # a removal that fails says the incomplete file stays
        note, created, removed, files = self.run_unwrap('X.AS', good, fault=5)
        self.assertEqual((note, removed, list(files)),
                         ('Cleanup failed: the incomplete file stays.', ['DOC'], ['DOC']))


if __name__ == '__main__':
    unittest.main()
