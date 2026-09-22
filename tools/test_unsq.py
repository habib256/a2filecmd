"""UNSQ's real entry point on the host, against tools/squeeze_ref.py.

The overlay (src/plugins/unsq.c) runs with the host's files and a CREATE
stand-in behind its service table. Every extraction is compared with the
reference -- names, types, bytes, the note -- for synthetic SQueezed files
and ACU archives, and for CiderPress II's real ones when at hand: the .QQ
inside its Binary II sample (whose plain original sits next to it) and
IconEd.ACU. Damaged input and failed writes leave nothing behind.
"""
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import squeeze_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402
from test_six_plugins import PREFIX, ROOT  # noqa: E402

HARNESS = PREFIX + r'''
#include "src/plugins/unsq.c"
static int fault, writes;
static FILE* writing;
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
static FILE* open_(const char* p, const char* m)
{
    FILE* f = fopen(p, m);
    if (!strcmp(m, "wb")) writing = f;
    return f;
}
static size_t write_(const void* p, size_t s, size_t n, FILE* f)
{
    if ((fault == 1 || fault == 4) && ++writes == 2) return n - 1;
    if (fault == 3 && ++writes == 1) {  /* a byte lands wrong: only the read-back sees it */
        unsigned char c[512];
        memcpy(c, p, n); c[0] ^= 1;
        return fwrite(c, s, n, f);
    }
    return fwrite(p, s, n, f);
}
static int close_(FILE* f)
{
    if (fault == 2 && f == writing) fputc('!', f);
    return fclose(f);
}
static int remove_(const char* p) { printf("REMOVE %s\n", strrchr(p, '/') + 1); return fault == 4 ? -1 : remove(p); }
static size_t read_(void* p, size_t s, size_t n, FILE* f) { return fread(p, s, n, f); }
static int seek_(FILE* f, long o, int w) { return fseek(f, o, w); }
static unsigned long bars, overflows;
static void bar_(const char* n, unsigned long d, unsigned long t) { ++bars; if (d > t || !*n) ++overflows; }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry sel;
    static char full[80], note[120];
    static unsigned char active, copy[512];
    strcpy(panels[0].path, argv[1]);
    strcpy(panels[1].path, argv[2]);
    strcpy(sel.name, argv[3]);
    sel.type = strtol(argv[4], 0, 16);
    sel.aux = strtol(argv[5], 0, 16);
    fault = atoi(argv[6]);
    sprintf(full, "%s/%s", argv[1], argv[3]);
    api.panels = panels; api.active = &active; api.selected = &sel; api.full = full;
    api.note = note; api.copy_buf = copy;
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy; api.strlen = strlen;
    api.strcmp = strcmp; api.sprintf = sprintf; api.fopen = open_; api.fread = read_;
    api.fwrite = write_; api.fseek = seek_; api.fclose = close_; api.remove = remove_;
    api.mli = mli_; api.progress_bar = bar_;
    {
        FILE* f = fopen(full, "rb");
        if (f) { fseek(f, 0, SEEK_END); sel.size = ftell(f); fclose(f); }
    }
    plugin_entry(&api);
    printf("BARS %lu %lu\n", bars, overflows);
    printf("NOTE %s\n", note);
    return 0;
}
'''


def bqy_members(data):
    out, pos = {}, 0
    while pos + 128 <= len(data):
        h = data[pos:pos + 128]
        if h[0:3] != b'\x0aGL':
            pos += 128
            continue
        eof = int.from_bytes(h[0x14:0x17], 'little')
        name = h[0x18:0x18 + h[0x17]].decode('latin-1')
        out[name] = data[pos + 128:pos + 128 + eof]
        pos += 128 + (eof + 127) // 128 * 128
    return out


class Unsq(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unsq-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'test.c').write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.root / 'test.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_unsq(self, name, data, typ=4, aux=0, fault=0, existing=()):
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        (case / 'S' / name).write_bytes(data)
        for e in existing:
            (case / 'D' / e).write_bytes(b'old')
        out = subprocess.run([str(self.exe), str(case / 'S'), str(case / 'D'), name,
                              '%02X' % typ, '%04X' % aux, str(fault)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        note = [l[5:] for l in lines if l.startswith('NOTE ')][0]
        created = [l.split()[1:] for l in lines if l.startswith('CREATE ')]
        removed = [l.split()[1] for l in lines if l.startswith('REMOVE ')]
        self.bars = [int(v) for l in lines if l.startswith('BARS ') for v in l.split()[1:]]
        made = {p.name: p.read_bytes() for p in (case / 'D').iterdir()}
        return note, created, removed, made

    def check(self, name, data, typ=4, aux=0):
        files = ref.unsqueeze(data, name)
        note, created, removed, made = self.run_unsq(name, data, typ, aux)
        want_created = [[n, '%02X' % (typ if t is None else t), '%04X' % (aux if a is None else a)]
                        for n, t, a, _ in files]
        self.assertEqual(created, want_created, note)
        self.assertEqual(made, {n: b for n, _, _, b in files})
        self.assertEqual(note, '%d extracted, 0 skipped (name taken).' % len(files))

    def test_squeezed_files(self):
        rng = random.Random(1)
        for i in range(30):
            size = rng.choice([0, 1, 2, 3, 200, 513, 4000])
            alphabet = rng.choice([b'ab', b'\x90\x90\x90a', bytes(range(256)), b'zzzzzzzzzy'])
            data = bytes(rng.choice(alphabet) for _ in range(size))
            name = rng.choice([b'NOTES.TXT', b'/usr/src/Read Me', b'', b'1.2.3', b'Mac:Folder:File'])
            with self.subTest(i=i):
                self.check('F%d.QQ' % i, ref.squeeze(data, name), typ=rng.choice([4, 6]),
                           aux=rng.randrange(0x10000))

    def test_acu_archives(self):
        rng = random.Random(2)
        for i in range(10):
            files = []
            for k in range(rng.randint(1, 6)):
                data = bytes(rng.choice(b'hello \x90\r') for _ in range(rng.choice([0, 5, 300, 2000])))
                if rng.random() < 0.2:
                    files.append((b'DIR%d' % k, 0x0F, 0, b'', False, True))
                files.append((b'DIR/FILE%d' % k, rng.choice([4, 6, 0xB3]), rng.randrange(65536),
                              data, rng.random() < 0.6, False))
            with self.subTest(i=i):
                self.check('A%d.ACU' % i, ref.make_acu(files), typ=0xE0, aux=0x8001)

    def test_real_files(self):
        found = 0
        bqy = cp2_samples.path('bny/SAMPLE.BQY')
        if bqy:
            found += 1
            members = bqy_members(bqy.read_bytes())
            qq = members['SQUEEZE/BNYARCHIVE.H.QQ']
            self.check('BNYARCHIVE.H.QQ', qq)
            self.assertEqual(ref.unsqueeze(qq, 'X')[0][3], members['BNYARCHIVE.H'])
        acu = cp2_samples.path('acu/IconEd.ACU')
        if acu:
            found += 1
            self.check('ICONED.ACU', acu.read_bytes(), typ=0xE0, aux=0x8001)
        if not found:
            self.skipTest('no CiderPress II samples')

    def test_progress(self):
        # Minutes at 1 MHz for a big file: the bar must move during the
        # decoding (every KB written) and the read-back (every block).
        rng = random.Random(3)
        data = bytes(rng.choice(b'abcdefgh \r') for _ in range(20000))
        self.check('BIG.QQ', ref.squeeze(data, b'BIG'))
        calls, bad = self.bars
        self.assertGreaterEqual(calls, 20000 // 1024 + 20000 // 512)
        self.assertEqual(bad, 0)
        acu = ref.make_acu([(b'A', 4, 0, data, True, False), (b'B', 4, 0, data[:3000], False, False)])
        self.check('BIG.ACU', acu, typ=0xE0, aux=0x8001)
        calls, bad = self.bars
        self.assertGreaterEqual(calls, 23000 // 1024 + 23000 // 512)
        self.assertEqual(bad, 0)

    def test_damage_and_failures(self):
        good = ref.squeeze(b'the same text, the same text, the same text\r' * 40, b'TEXT')
        cases = [good[:-3], good[:30], good[:2] + bytes([good[2] ^ 1]) + good[3:],
                 good[:18] + b'\x01\x02' + good[20:], b'\x76\xff\x00\x00NAME',
                 b'plain text, neither format' * 3]
        for data in cases:
            with self.subTest(data=data[:12]):
                note, created, removed, made = self.run_unsq('BAD.QQ', data)
                self.assertEqual(made, {}, note)
        acu = ref.make_acu([(b'A', 4, 0, b'first\r' * 30, True, False), (b'B', 4, 0, b'x' * 99, False, False)])
        note, created, removed, made = self.run_unsq('X.ACU', acu[:-10])
        self.assertEqual(list(made), ['A'], note)
        self.assertTrue(note.endswith('damaged, stopped.'), note)
        bad_len = bytearray(acu)
        bad_len[20 + 0x26] ^= 1
        note, created, removed, made = self.run_unsq('X.ACU', bytes(bad_len))
        self.assertEqual((made, removed), ({}, ['A']), note)
        # a squeezed fork one byte shorter than its stream, the byte after it
        short = bytearray(ref.make_acu([(b'A', 4, 0, b'first\r' * 30, True, False)]))
        short[20 + 0x12] -= 1
        self.assertRaises(ref.Bad, ref.unsqueeze, bytes(short), 'X')
        note, created, removed, made = self.run_unsq('X.ACU', bytes(short))
        self.assertEqual(made, {}, note)
        note, created, removed, made = self.run_unsq('X.ACU', acu, existing=['A'])
        self.assertEqual((note, made['B']), ('1 extracted, 1 skipped (name taken).', b'x' * 99))
        for fault in (1, 2, 3):
            with self.subTest(fault=fault):
                note, created, removed, made = self.run_unsq('T.QQ', good, fault=fault)
                self.assertEqual((made, removed), ({}, ['TEXT']), note)
        note, created, removed, made = self.run_unsq('T.QQ', good, fault=4)
        self.assertIn('Cleanup failed', note)


if __name__ == '__main__':
    unittest.main()
