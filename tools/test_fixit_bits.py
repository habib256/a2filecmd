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


if __name__ == '__main__':
    unittest.main()
