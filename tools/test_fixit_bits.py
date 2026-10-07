"""Run the claim bitmap of FIXIT and REPAIR (src/plugins/fixit_bits.inc) under sim65.

The walker in fixit_walk.h asks two questions of it, bit_test and bit_set,
and the host tests answer them with a C model (FIXIT_HOST). This harness runs
the real assembly on both processors instead, against a Python model: in the
main bank, where the bits of a volume of up to 4 096 blocks live in seen[],
and in the auxiliary one, $4000-$5FFF, for all 65 536 blocks.

sim65 has no auxiliary bank: the soft switches ($C002-$C005) are plain RAM
and $4000 is main memory, so what is checked here is the arithmetic -- the
byte and the bit of a block, the answer, what is written and what is not,
the clearing of the 8 KB, and a mirror copy that leaves the code intact. The
switching itself is bench/fixit.py's, under POM2.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Above the auxiliary bitmap ($4000-$5FFF) and below the soft switches the
# code writes ($C002-$C005), which sim65 treats as plain RAM.
CFG_START = '$6000'

HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
unsigned char seen[512];
unsigned char aux;
unsigned char __fastcall__ bit_test(unsigned int b);
unsigned char __fastcall__ bit_set(unsigned int b);
void bit_init(void);
extern unsigned char mirror_start[], mirror_end[];
static unsigned char op[3], r[2];
int main(void)
{
    int in;
    unsigned int b, x;
    in = open("ops.bin", O_RDONLY);
    if (in < 0) return 10;
    memset((void*)0x3000, 0xEE, 0x1000);    /* below the bitmap: never touched */
    memset((void*)0x4000, 0xFF, 0x2000);    /* stale AUX: a /RAM disk was there */
    memset(seen, 0x55, sizeof seen);
    while (read(in, op, 3) == 3) {
        b = op[1] | ((unsigned int)op[2] << 8);
        x = 0;
        switch (op[0]) {
        case 'M': aux = 0; memset(seen, 0, sizeof seen); r[0] = 0; break;
        case 'A': aux = 1; bit_init(); r[0] = 0; break;
        case 'T': x = bit_test(b); r[0] = (unsigned char)x; break;
        case 'S': x = bit_set(b); r[0] = (unsigned char)x; break;
        default: return 11;
        }
        r[1] = (unsigned char)(x >> 8);         /* X must come back 0 */
        if (write(1, r, 2) != 2) return 12;
    }
    if (write(1, seen, sizeof seen) != sizeof seen) return 13;
    if (write(1, (void*)0x3000, 0x3000) != 0x3000) return 14;
    return 0;
}
'''

ASM = '''
        .include "fixit_bits.inc"
        .export _mirror_start := mirror_start, _mirror_end := mirror_end
'''


class Model:
    """What the two banks must hold after the same operations."""

    def __init__(self):
        self.seen = bytearray([0x55] * 512)
        self.aux = bytearray([0xFF] * 0x2000)
        self.use_aux = False

    def apply(self, kind, b):
        if kind == 'M':
            self.use_aux = False
            self.seen = bytearray(512)
            return 0
        if kind == 'A':
            self.use_aux = True
            self.aux = bytearray(0x2000)
            return 0
        bank = self.aux if self.use_aux else self.seen
        mask = 0x80 >> (b & 7)
        old = bank[b >> 3] & mask
        if kind == 'S':
            bank[b >> 3] |= mask
        return old


def script(seed, n=3000):
    rnd = random.Random(seed)
    ops = [('M', 0)]
    for i in range(n):
        if i == n // 2:
            ops.append(('A', 0))
        aux = i >= n // 2
        limit = 65536 if aux else 4096
        b = rnd.choice((0, 1, 7, 8, 255, 256, 511, 512, 4095,
                        limit - 1, limit - 8, rnd.randrange(limit), rnd.randrange(limit)))
        ops.append((rnd.choice('TSS'), b))
    ops.append(('M', 0))                        # back to the main bank
    ops += [(rnd.choice('TS'), rnd.randrange(4096)) for _ in range(200)]
    ops.append(('A', 0))                        # a second pass clears again
    ops += [(rnd.choice('TS'), rnd.randrange(65536)) for _ in range(200)]
    return ops


class FixitBits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-fixit-bits-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/fixit_bits.inc', cls.dir / 'fixit_bits.inc')
        (cls.dir / 'bits.s').write_text(ASM)
        (cls.dir / 'harness.c').write_text(HARNESS)
        cls.programs = {}
        for cpu in ('6502', '65c02'):
            base = 'sim65c02' if cpu == '65c02' else 'sim6502'
            cfg = (target.parent / f'cfg/{base}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              f'start = {CFG_START}, size = $BF00 - {CFG_START} - __STACKSIZE__')
            (cls.dir / f'{cpu}.cfg').write_text(cfg)
            exe = cls.dir / f'harness-{cpu}'
            subprocess.run(['cl65', '-t', 'sim6502' if cpu == '6502' else 'sim65c02',
                            '-C', str(cls.dir / f'{cpu}.cfg'), '-O',
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'bits.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_ops(self, cpu, ops):
        data = b''.join(bytes([ord(k), b & 255, b >> 8]) for k, b in ops)
        (self.dir / 'ops.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu])], cwd=self.dir,
                             capture_output=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_both_banks_against_the_model(self):
        for cpu in self.programs:
            for seed in (1, 2, 3):
                with self.subTest(cpu=cpu, seed=seed):
                    ops = script(seed)
                    out = self.run_ops(cpu, ops)
                    model = Model()
                    answers = [model.apply(k, b) for k, b in ops]
                    got = [out[2 * i] for i in range(len(ops))]
                    self.assertEqual(got, answers)
                    self.assertEqual(set(out[2 * i + 1] for i in range(len(ops))), {0},
                                     'X is 0 on return')
                    tail = out[2 * len(ops):]
                    self.assertEqual(tail[:512], bytes(model.seen), 'seen[]')
                    self.assertEqual(tail[512:512 + 0x1000], b'\xee' * 0x1000,
                                     'nothing below $4000 is written')
                    self.assertEqual(tail[512 + 0x1000:], bytes(model.aux), '$4000-$5FFF')

    def test_the_mirror_fits_in_one_copy_loop(self):
        text = (ROOT / 'src/plugins/fixit_bits.inc').read_text()
        self.assertIn('.assert mirror_end - mirror_start < 256', text)
        # Everything that runs while RAMRD is on sits between the two labels.
        body = text[text.index('mirror_start:'):text.index('mirror_end:')]
        for switch in ('RDAUX', 'RDMAIN'):
            self.assertIn(switch, body)
        before = text[:text.index('mirror_start:')]
        self.assertNotIn('sta     RDAUX', before, 'no RAMRD outside the mirror')


# -- src/plugins/fixit_asm.inc: first_part, and REPAIR's samebytes and swap --
# The host harnesses of tools/test_fixit.py and test_repair.py compile the C
# versions (FIXIT_HOST); the Apple II runs these. Bug hunt 2 wrote them for
# their size, and the first swap kept its count in Y across popax, which
# loads Y: the loop then swapped 256 bytes. bench/repair.py caught it under
# POM2 (a BRK after FIX on the directory plan); this harness now runs the
# real assembly with a guard band around every buffer, on both processors.
ASM_HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
union { unsigned int w; unsigned char b[5]; } nu;
static unsigned char guard_a[8];
unsigned char nu_after[8];
void __fastcall__ first_part(char* dst, const char* path);
unsigned char __fastcall__ samebytes(const unsigned char* a, const unsigned char* b, unsigned int n);
void __fastcall__ swap(unsigned char* p, unsigned char n);
static unsigned char a[600], b[600], blk[64];
static char path[80], dst[40];
static unsigned char hdr[4], r[2];
int main(void)
{
    int in;
    unsigned int n, off, i;
    unsigned char k, x;
    in = open("asm.bin", O_RDONLY);
    if (in < 0) return 10;
    while (read(in, hdr, 4) == 4) {
        k = hdr[0];
        n = hdr[1] | ((unsigned int)hdr[2] << 8);
        off = hdr[3];
        if (k == 'P') {                         /* first_part: path of n bytes */
            memset(path, 0, sizeof path);
            if (read(in, path, n) != (int)n) return 11;
            memset(dst, 0xEE, sizeof dst);
            first_part(dst + 4, path);
            if (write(1, dst, sizeof dst) != sizeof dst) return 12;
        } else if (k == 'C') {                  /* samebytes over n, a differing byte at off-1 */
            for (i = 0; i < sizeof a; ++i) a[i] = b[i] = (unsigned char)(i * 7);
            if (off) b[4 + off - 1 + (n > 255 ? 256 : 0)] ^= 1;
            r[0] = samebytes(a + 4, b + 4, n);
            r[1] = 0;
            if (write(1, r, 2) != 2) return 13;
        } else if (k == 'S') {                  /* swap n bytes at blk+off */
            for (i = 0; i < sizeof blk; ++i) blk[i] = (unsigned char)(0x80 + i);
            for (i = 0; i < 5; ++i) nu.b[i] = (unsigned char)(0x10 + i);
            memset(guard_a, 0x77, sizeof guard_a);
            swap(blk + off, (unsigned char)n);
            if (write(1, blk, sizeof blk) != sizeof blk) return 14;
            if (write(1, nu.b, 5) != 5) return 15;
            if (write(1, guard_a, sizeof guard_a) != sizeof guard_a) return 16;
        } else return 17;
        (void)x;
    }
    return 0;
}
'''

ASM_INC = '''
REPAIR_ASM = 1
        .include "fixit_asm.inc"
'''


class FixitAsm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-fixit-asm-')
        cls.dir = Path(cls.tmp.name)
        shutil.copyfile(ROOT / 'src/plugins/fixit_asm.inc', cls.dir / 'fixit_asm.inc')
        (cls.dir / 'asm.s').write_text(ASM_INC)
        (cls.dir / 'harness.c').write_text(ASM_HARNESS)
        cls.programs = {}
        for cpu in ('6502', '65c02'):
            exe = cls.dir / f'asm-{cpu}'
            subprocess.run(['cl65', '-t', 'sim6502' if cpu == '6502' else 'sim65c02', '-O',
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'asm.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_asm(self, cpu, data):
        (self.dir / 'asm.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu])], cwd=self.dir,
                             capture_output=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_first_part_is_the_c_loop(self):
        def model(p):
            out = ''
            for k, c in enumerate(p[:16]):
                if k and c == '/':
                    break
                out += c
            return out
        paths = ['/VOL', '/VOL/SUB/FILE', '/', '', 'X', 'NOSLASH/X',
                 '/ABCDEFGHIJKLMNOPQRS/T', '/ABCDEFGHIJKLMNO', '/ABCDEFGHIJKLMNOP/X', '//X']
        data = b''.join(bytes([ord('P'), len(p), 0, 0]) + p.encode() for p in paths)
        for cpu in self.programs:
            out = self.run_asm(cpu, data)
            for i, p in enumerate(paths):
                with self.subTest(cpu=cpu, path=p):
                    got = out[40 * i:40 * (i + 1)]
                    want = model(p).encode()
                    self.assertEqual(got[:4], b'\xee' * 4, 'nothing before dst')
                    self.assertEqual(got[4:4 + len(want) + 1], want + b'\0')
                    self.assertEqual(got[4 + len(want) + 1:], b'\xee' * (35 - len(want)),
                                     'nothing after the terminator')

    def test_samebytes_counts_n_and_finds_any_difference(self):
        cases = []
        for n in (0, 1, 2, 39, 255, 256, 257, 512):
            cases.append((n, 0, 1))                       # equal
            if n:
                cases.append((n, 1, 0))                   # first byte differs
                if n <= 255:
                    cases.append((n, n, 0))               # last byte differs
                if n < 255:
                    cases.append((n, n + 1, 1))           # one past the end: not compared
        # a difference in the second page: off is the byte inside page 2
        cases += [(512, 1, 0), (512, 255, 0), (300, 44, 0), (300, 45, 1)]
        data = b''.join(bytes([ord('C'), n & 255, n >> 8, off]) for n, off, _ in cases)
        for cpu in self.programs:
            out = self.run_asm(cpu, data)
            for i, (n, off, want) in enumerate(cases):
                # where the harness plants the difference: inside page 2 for
                # n > 255, so the same `off` byte reaches the second page
                pos = off - 1 + (256 if n > 255 else 0)
                want = 0 if off and pos < n else 1
                with self.subTest(cpu=cpu, n=n, off=off):
                    self.assertEqual((out[2 * i], out[2 * i + 1]), (want, 0))

    def test_swap_exchanges_n_bytes_and_nothing_else(self):
        cases = [(n, off) for n in (1, 2, 4, 5) for off in (0, 3, 20)]
        data = b''.join(bytes([ord('S'), n, 0, off]) for n, off in cases)
        for cpu in self.programs:
            out = self.run_asm(cpu, data)
            step = 64 + 5 + 8
            for i, (n, off) in enumerate(cases):
                with self.subTest(cpu=cpu, n=n, off=off):
                    got = out[step * i:step * (i + 1)]
                    blk = bytearray(0x80 + j for j in range(64))
                    nu = bytearray(0x10 + j for j in range(5))
                    for j in range(n):
                        blk[off + j], nu[j] = nu[j], blk[off + j]
                    self.assertEqual(got[:64], bytes(blk), 'blk')
                    self.assertEqual(got[64:69], bytes(nu), 'nu')
                    self.assertEqual(got[69:], b'\x77' * 8, 'the guard next to nu')


if __name__ == '__main__':
    unittest.main()
