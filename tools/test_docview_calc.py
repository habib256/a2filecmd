"""DOCVIEW's arithmetic (src/plugins/docview.s) on the real Applesoft ROM.

fp_op runs under sim65 with an Apple II ROM at $D000 (A2FC_ROM; POM2's
apple2p.rom by default), as test_awdata.py runs FOUT: every operation,
comparison and function against Python's own arithmetic on the ROM's
5-byte numbers, and above all the errors. Division by zero, an overflow, the
logarithm or the square root of a negative number go to Applesoft's ERROR,
which would leave for BASIC; fp_op must come back with 1, fp_x unchanged,
the zero page $50-$FF as it was and the stack where it was -- hundreds of
times in a row.
"""
import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM = Path(os.environ.get('A2FC_ROM', str(Path.home() / 'src/pom2/roms/apple2p.rom')))

OPS = ['ADD', 'SUB', 'MUL', 'DIV', 'POW', 'LT', 'GT', 'EQ', 'NE', 'LE', 'GE',
       'SIN', 'COS', 'TAN', 'ATN', 'LOG', 'EXP', 'SGN', 'ABS', 'SQR', 'INT', 'NEG',
       'INT16', 'FOUT']
OP = {n: i for i, n in enumerate(OPS)}


def pack(v):
    """A Python float as the ROM's 5 bytes (rounded to 32 bits of mantissa)."""
    if v == 0:
        return bytes(5)
    m, e = math.frexp(abs(v))                 # v = m * 2**e, 0.5 <= m < 1
    mant = round(m * 2 ** 32)
    if mant == 2 ** 32:
        mant, e = 2 ** 31, e + 1
    assert 0 < e + 128 < 256, v
    b = mant.to_bytes(4, 'big')
    return bytes([e + 128, (b[0] & 0x7F) | (0x80 if v < 0 else 0)]) + b[1:]


def unpack(b):
    if b[0] == 0:
        return 0.0
    mant = int.from_bytes(bytes([b[1] | 0x80]) + b[2:5], 'big')
    v = mant / 2 ** 32 * 2.0 ** (b[0] - 128)
    return -v if b[1] & 0x80 else v


HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
extern unsigned char fp_x[5], fp_y[5], fp_text[17];
extern int fp_n;
extern unsigned char* fp_zsave;
unsigned char __fastcall__ fp_op(unsigned char op);
static unsigned char zsave[0xB0];                  /* DOCVIEW gives part of copy_buf */
int main(void)
{
    unsigned char rec[13], out[24], i, bad;
    int in = open("rom.bin", O_RDONLY);
    fp_zsave = zsave;
    if (read(in, (void*)0xD000, 0x3000) != 0x3000) return 9;
    close(in);
    in = open("ops.bin", O_RDONLY);
    while (read(in, rec, 13) == 13) {
        memcpy(fp_x, rec + 1, 5);
        memcpy(fp_y, rec + 6, 5);
        fp_n = rec[11] | rec[12] << 8;
        for (i = 0x50; i; ++i) *(unsigned char*)i = i ^ 0xA5;    /* the caller's zero page */
        out[0] = fp_op(rec[0]);
        bad = 0;
        for (i = 0x50; i; ++i) if (*(unsigned char*)i != (i ^ 0xA5)) bad = 1;
        out[1] = bad;
        memcpy(out + 2, fp_x, 5);
        memcpy(out + 7, fp_text, 17);
        write(1, out, 24);
    }
    return 0;
}
'''


class DocviewCalc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ROM.exists():
            raise unittest.SkipTest('no Apple II ROM image (A2FC_ROM)')
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-dvcalc-')
        d = Path(cls.tmp.name)
        (d / 'rom.bin').write_bytes(ROM.read_bytes()[-0x3000:])
        (d / 'h.c').write_text(HARNESS)
        shutil.copyfile(ROOT / 'src/plugins/docview.s', d / 'docview.s')   # cl65 writes beside it
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        cls.exe = {}
        for cpu in ('sim6502', 'sim65c02'):
            cfg = (target.parent / f'cfg/{cpu}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              'start = $0800, size = $C000 - $0800 - __STACKSIZE__')
            assert '$C000 - $0800' in cfg
            (d / f'{cpu}.cfg').write_text(cfg)
            exe = d / f'calc-{cpu}'
            subprocess.run(['cl65', '-t', cpu, '-C', str(d / f'{cpu}.cfg'), '-O', '-o', str(exe),
                            str(d / 'h.c'), str(d / 'docview.s')],
                           check=True, cwd=d, capture_output=True)
            cls.exe[cpu] = exe
        cls.dir = d

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_ops(self, recs):
        (self.dir / 'ops.bin').write_bytes(b''.join(
            bytes([OP[op]]) + pack(x) + pack(y) + struct.pack('<h', n) for op, x, y, n in recs))
        results = {}
        for cpu, exe in self.exe.items():
            p = subprocess.run(['sim65', str(exe)], cwd=self.dir, capture_output=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stderr)
            o = p.stdout
            self.assertEqual(len(o), 24 * len(recs), cpu)
            res = []
            for k in range(len(recs)):
                r = o[24 * k:24 * k + 24]
                self.assertEqual(r[1], 0, '%s: the zero page $50-$FF was not put back (%r)' % (cpu, recs[k]))
                res.append((r[0], unpack(r[2:7]), r[7:24].split(b'\0')[0].decode()))
            results[cpu] = res
        self.assertEqual(results['sim6502'], results['sim65c02'])
        return results['sim6502']

    def close(self, got, want, what):
        self.assertTrue(math.isclose(got, want, rel_tol=2e-9, abs_tol=1e-30), (what, got, want))

    def test_arithmetic_and_functions(self):
        rng = random.Random(1987)
        pairs = [(1650, 18.6), (10949, 1662), (-2.5, 4), (0.1, 3), (1e10, -3e-5), (7, 7), (0, 5)]
        pairs += [(rng.uniform(-1e6, 1e6), rng.uniform(-1e3, 1e3)) for _ in range(40)]
        recs, want = [], []
        py = {'ADD': lambda x, y: x + y, 'SUB': lambda x, y: x - y, 'MUL': lambda x, y: x * y,
              'DIV': lambda x, y: x / y, 'LT': lambda x, y: float(x < y), 'GT': lambda x, y: float(x > y),
              'EQ': lambda x, y: float(x == y), 'NE': lambda x, y: float(x != y),
              'LE': lambda x, y: float(x <= y), 'GE': lambda x, y: float(x >= y)}
        for x, y in pairs:
            x, y = unpack(pack(x)), unpack(pack(y))
            for op, f in py.items():
                recs.append((op, x, y, 0)); want.append(f(x, y))
        for x in (1, 2, 0.5, 12, -14, 9, 3.7, -3.7, 100, 1e-3):
            for op, f in (('SIN', math.sin), ('COS', math.cos), ('TAN', math.tan), ('ATN', math.atan),
                          ('EXP', math.exp), ('SGN', lambda v: float((v > 0) - (v < 0))),
                          ('ABS', abs), ('INT', lambda v: float(math.floor(v))), ('NEG', lambda v: -v)):
                if op == 'EXP' and x > 88:
                    continue                   # an overflow: test_errors_come_back
                recs.append((op, x, 0, 0)); want.append(f(x))
            if x > 0:
                recs.append(('LOG', x, 0, 0)); want.append(math.log(x))
                recs.append(('SQR', x, 0, 0)); want.append(math.sqrt(x))
        for x, y in ((2, 10), (9, 0.5), (1.5, 3), (10, -2), (5, 0)):
            recs.append(('POW', x, y, 0)); want.append(x ** y)
        for n in (0, 1, -1, 12, 1662, 32767, -32768):
            recs.append(('INT16', 99, 0, n)); want.append(float(n))
        res = self.run_ops(recs)
        for (err, got, _), w, r in zip(res, want, recs):
            self.assertEqual(err, 0, r)
            if r[0] in ('SIN', 'COS', 'TAN', 'ATN', 'LOG', 'EXP', 'SQR', 'POW'):
                self.assertTrue(math.isclose(got, w, rel_tol=1e-7, abs_tol=1e-8), (r, got, w))   # ~9 digits, fewer after argument reduction
            else:
                self.close(got, w, r)

    def test_fout(self):
        res = self.run_ops([('FOUT', v, 0, 0) for v in (12, 0.5, -2.25, 10949, 1e10, 0)])
        self.assertEqual([t for _, _, t in res], ['12', '.5', '-2.25', '10949', '1E+10', '0'])

    def test_errors_come_back(self):
        # Each one would print ?DIVISION BY ZERO ERROR, ?OVERFLOW ERROR or
        # ?ILLEGAL QUANTITY ERROR and leave for BASIC without the trap.
        bad = [('DIV', 5, 0), ('MUL', 1e38, 1e38), ('ADD', 1.7e38, 1.7e38), ('EXP', 100, 0),
               ('LOG', 0, 0), ('LOG', -3, 0), ('SQR', -9, 0), ('POW', -8, 0.5), ('DIV', 1e38, 1e-38)]
        recs = []
        for k in range(40):                    # 360 errors: a leaked stack would not survive
            recs += [(op, x, y, 0) for op, x, y in bad]
            recs.append(('ADD', 2, k, 0))          # and a good one in between
        res = self.run_ops(recs)
        for (err, got, _), (op, x, y, _) in zip(res, recs):
            if op == 'ADD' and x == 2:
                self.assertEqual((err, got), (0, 2 + y))
            else:
                self.assertEqual(err, 1, (op, x, y))
                self.close(got, unpack(pack(x)), 'fp_x unchanged after %s' % op)


if __name__ == '__main__':
    unittest.main()
