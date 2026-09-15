"""Run the real UNSHRINK assembly core (src/unshrink.s) under sim65.

The C driver in a2fc.c feeds us_chunk from an input window and writes
OUTBUF; this harness does the same with a host file, so the bytes decoded
by the 6502 are compared with the data mkshk.py compressed. Malformed
streams must be refused (us_chunk returns 0) instead of hanging the
machine or writing outside the AUX windows.
"""
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mkshk  # noqa: E402

# The program lives above the core's AUX map ($2000-$9FFF) and above the
# soft switches it writes ($C002-$C005), which sim65 treats as plain RAM.
CFG_START = '$C100'

HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
void __fastcall__ us_init(unsigned int fmt_esc);
unsigned int __fastcall__ us_chunk(unsigned int in_addr);
#define INBUF 0x6000u
#define WINDOW 0x2000u
static unsigned char hdr[4];
int main(void)
{
    int in, got;
    unsigned int total, n, used, win_len = 0, win_pos = 0;
    unsigned char fmt, h;
    in = open("in.bin", O_RDONLY);
    if (in < 0) return 10;
    if (read(in, hdr, 3) != 3) return 11;
    fmt = hdr[0];
    total = hdr[1] | ((unsigned int)hdr[2] << 8);
    h = fmt == 2 ? 4 : 2;
    if (read(in, hdr, h) != h) return 12;
    memset((void*)0x2000, 0xFF, 0x8000);   /* stale AUX: a /RAM disk was there */
    us_init(((unsigned int)hdr[h - 1] << 8) | fmt);
    while (total) {
        if (win_len - win_pos < 4100) {
            memmove((void*)INBUF, (void*)(INBUF + win_pos), win_len - win_pos);
            win_len -= win_pos;
            win_pos = 0;
            got = read(in, (void*)(INBUF + win_len), WINDOW - win_len);
            if (got < 0) return 13;
            win_len += got;
        }
        used = us_chunk(INBUF + win_pos);
        if (!used || used > win_len - win_pos) return 2;
        win_pos += used;
        n = total > 4096 ? 4096 : total;
        if (write(1, (void*)0x8000, n) != n) return 14;
        total -= n;
    }
    return 0;
}
'''


def runs(seed, size):
    """Binary data made of runs of every length up to 300, ESC included."""
    rnd, out = random.Random(seed), bytearray()
    while len(out) < size:
        v = rnd.choice((0x00, 0xFF, mkshk.ESC, rnd.randrange(256)))
        out += bytes([v]) * rnd.choice((1, 2, 3, 4, 5, 128, 129, 130, 131, 200, 255, 256, 257, 300))
    return bytes(out[:size])


def lzw1_chunk(codes, rlelen=mkshk.CHUNK):
    """One hand-made LZW/1 chunk: header, then codes at the decoder's widths."""
    acc = nbits = 0
    entry, fresh, body = mkshk.FIRST, True, bytearray()
    for code in codes:
        acc |= code << nbits
        nbits += mkshk.code_width(entry)
        while nbits >= 8:
            body.append(acc & 0xFF)
            acc, nbits = acc >> 8, nbits - 8
        if fresh:
            fresh = False
        else:
            entry += 1
    if nbits:
        body.append(acc & 0xFF)
    return struct.pack('<HB', rlelen, 1) + bytes(body)


class UnshrinkCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-unshrink-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        cls.programs = {}
        src = (ROOT / 'src/unshrink.s').read_text()
        # the AUX-mirror assert is about the real $1B00 load address
        src = src.replace('.assert us_end <= $2000', '.assert us_end <= $FFFF')
        (cls.dir / 'unshrink.s').write_text(src)
        (cls.dir / 'harness.c').write_text(HARNESS)
        for cpu in ('6502', '65c02'):
            base = 'sim65c02' if cpu == '65c02' else 'sim6502'
            cfg = (target.parent / f'cfg/{base}.cfg').read_text()
            cfg = cfg.replace('start = $0200, size = $FDF0 - __STACKSIZE__',
                              f'start = {CFG_START}, size = $FDF0 - {CFG_START} - __STACKSIZE__')
            cfg = cfg.replace('    CODE:     load = MAIN,   type = ro;',
                              '    CODE:     load = MAIN,   type = ro;\n'
                              '    UNSHRINK: load = MAIN,   type = ro;')
            (cls.dir / f'{cpu}.cfg').write_text(cfg)
            exe = cls.dir / f'harness-{cpu}'
            subprocess.run([shutil.which('cl65'), '-t', base, '--cpu', cpu, '-C', str(cls.dir / f'{cpu}.cfg'),
                            '-O', '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'unshrink.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decode(self, cpu, fmt, stream, size):
        (self.dir / 'in.bin').write_bytes(struct.pack('<BH', fmt, size) + stream)
        run = subprocess.run([shutil.which('sim65'), str(self.programs[cpu])], cwd=self.dir,
                             stdout=subprocess.PIPE, timeout=60)
        return run.returncode, run.stdout

    def test_round_trip_both_formats(self):
        samples = {
            'long runs': runs(1, 12000),
            'zeros then text': bytes(6000) + b'SHRINKIT ON THE APPLE II. ' * 300,
            'incompressible': random.Random(7).randbytes(9000),
            'text, table clears': bytes(random.Random(3).choice(b'ABCDEFGH \r') for _ in range(40000))[:32000],
        }
        for cpu in self.programs:
            for fmt in (2, 3):
                for label, data in samples.items():
                    with self.subTest(cpu=cpu, fmt=fmt, data=label):
                        stream, _ = mkshk.shrink(data, fmt)
                        self.assertEqual(mkshk.unshrink(stream, fmt, len(data)), data)
                        rc, out = self.decode(cpu, fmt, stream, len(data))
                        self.assertEqual(rc, 0)
                        self.assertEqual(out, data)

    def test_malformed_streams_are_refused(self):
        head = b'\0\0' + bytes((mkshk.VOL, mkshk.ESC))
        cases = {
            'first code above $FF': [0x141, 0x41],
            'code beyond the next entry': [0x41, 0x42, 0x103, 0x103, 0x104],
            'LZW/1 code $100': [0x41, 0x100, 0x41],
        }
        for cpu in self.programs:
            for label, codes in cases.items():
                with self.subTest(cpu=cpu, case=label):
                    stream = head + lzw1_chunk(codes + [0x41] * 40, 0x1000) + bytes(64)
                    rc, _ = self.decode(cpu, 2, stream, 4096)
                    self.assertEqual(rc, 2)
            with self.subTest(cpu=cpu, case='RLE length above 4096'):
                stream = head + lzw1_chunk([0x41] * 200, 0x1800) + bytes(64)
                self.assertEqual(self.decode(cpu, 2, stream, 4096)[0], 2)
            with self.subTest(cpu=cpu, case='RLE run past the chunk'):
                body = bytes(4000) + bytes((mkshk.ESC, 0x55, 255))
                stream = head + struct.pack('<HB', len(body), 0) + body + bytes(64)
                self.assertEqual(self.decode(cpu, 2, stream, 4096)[0], 2)


if __name__ == '__main__':
    unittest.main()
