"""Run the MacPaint decoder (src/plugins/macpaint.s) under sim65.

The assembly unpacks the lines, notes where the views start, turns 560 dots
into double hi-res bytes and stores them. It runs here on both processors,
built with MP_TEST so that the auxiliary bytes -- written with RAMWRT on,
which sim65 does not have -- land 16 KB higher, at $6000, and the two planes
can be read apart. The reference is tools/macpaint_ref.py.

What the entry point adds -- the header checks, the seeks, the keys, the
/RAM rebuild, the messages -- is bench/macpaint.py's.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import macpaint_ref as ref  # noqa: E402
import cp2_samples  # noqa: E402

CFG_START = '$8000'

# argv: s (scan from argv[2]) or d (draw from argv[2]); argv[3] the chunk.
HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
unsigned char mp_scan(void);
unsigned char mp_draw(void);
extern unsigned int mp_pos, mp_ck[15];
unsigned char* mp_buf;
static unsigned char buf[255];
static int in, chunk;
unsigned char mp_read(void)
{
    int n = read(in, buf, chunk);
    return n > 0 ? (unsigned char)n : 0;
}
int main(int argc, char** argv)
{
    unsigned char r[1];
    unsigned int at = atoi(argv[2]);
    mp_buf = buf;
    chunk = atoi(argv[3]);
    memset((void*)0x2000, 0xEE, 0x6000);
    memset(mp_ck, 0xEE, sizeof mp_ck);
    in = open("pic.bin", O_RDONLY);
    if (in < 0) return 10;
    for (mp_pos = at; mp_pos; mp_pos -= r[0])      /* sim65 has no lseek */
        if (read(in, r, 1) != 1) break; else r[0] = 1;
    mp_pos = at;
    r[0] = argv[1][0] == 's' ? mp_scan() : mp_draw();
    if (write(1, r, 1) != 1) return 11;
    if (write(1, mp_ck, sizeof mp_ck) != sizeof mp_ck) return 16;
    if (write(1, &mp_pos, 2) != 2) return 17;
    if (write(1, (void*)0x2000, 0x2000) != 0x2000) return 12;   /* main */
    if (write(1, (void*)0x6000, 0x2000) != 0x2000) return 13;   /* aux */
    if (write(1, (void*)0x4000, 0x2000) != 0x2000) return 14;   /* never written */
    return 0;
}
'''


def visible(page):
    return b''.join(page[ref.row_address(y):ref.row_address(y) + 40] for y in range(192))


class MacPaint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-macpaint-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/macpaint.s', cls.dir / 'macpaint.s')
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
                            '--asm-define', 'MP_TEST', '-C', str(cls.dir / f'{cpu}.cfg'), '-O',
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'macpaint.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_mp(self, cpu, data, mode, at, chunk=255):
        (self.dir / 'pic.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu]), mode, str(at), str(chunk)],
                             cwd=self.dir, capture_output=True, timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr)
        o = out.stdout
        ck = [int.from_bytes(o[1 + 2 * i:3 + 2 * i], 'little') for i in range(15)]
        pos = int.from_bytes(o[31:33], 'little')
        return o[0], ck, pos, o[33:0x2021], o[0x2021:0x4021], o[0x4021:]

    def scan(self, cpu, data, chunk=255):
        """The checkpoints, checked against the reference."""
        start = ref.data_offset(data)
        k, ck, pos, main, aux, rest = self.run_mp(cpu, data, 's', start, chunk)
        self.assertEqual(k, 1)
        _, offsets = ref.unpack(data)
        self.assertEqual(ck, offsets[::48])
        self.assertEqual(main + aux + rest, b'\xee' * 0x6000, 'a scan stores nothing')
        return ck

    def draw(self, cpu, data, ck, top, chunk=255):
        k, _, _, main, aux, rest = self.run_mp(cpu, data, 'd', ck[top // 48], chunk)
        self.assertEqual(k, 1)
        want_aux, want_main = ref.screen(data, top)
        self.assertEqual(visible(main), visible(want_main), 'main plane, top %d' % top)
        self.assertEqual(visible(aux), visible(want_aux), 'auxiliary plane, top %d' % top)
        self.assertEqual(rest, b'\xee' * 0x2000, 'nothing written past the pages')

    def test_pictures_on_both_processors(self):
        rng = random.Random(7)
        for i in range(3):
            data = ref.pack(ref.random_lines(rng), rng, version=2 * (i % 2),
                            macbinary=i == 1, noise=i == 2)
            for cpu in self.programs:
                with self.subTest(cpu=cpu, picture=i):
                    chunk = rng.choice([255, 1, 7, 128])
                    ck = self.scan(cpu, data, chunk)
                    for top in (0, 96, 528):
                        self.draw(cpu, data, ck, top, rng.choice([255, 3]))

    def test_every_dot_lands_where_it_should(self):
        # one dot per line, walking across all 576 columns and back
        lines = []
        for y in range(720):
            line = bytearray(72)
            x = y % 576
            line[x // 8] = 0x80 >> (x % 8)
            lines.append(bytes(line))
        data = ref.pack(lines)
        for cpu in self.programs:
            ck = self.scan(cpu, data)
            for top in range(0, 529, 48):
                with self.subTest(cpu=cpu, top=top):
                    self.draw(cpu, data, ck, top)

    def test_bad_streams_are_refused(self):
        rng = random.Random(3)
        good = ref.pack(ref.random_lines(rng), rng)
        over = bytearray(good[:512])
        over += bytes([0xB7, 0x55])         # a run of 74: past its line
        over += good[512:]
        literal = bytearray(good[:512])
        literal += bytes([0, 0x11, 71]) + bytes(72)       # 1 + 72 literal bytes
        literal += good[512:]
        for cpu in self.programs:
            for name, data in (('cut', good[:-1]), ('half', good[:len(good) // 2]),
                               ('header only', good[:512]), ('run over', bytes(over)),
                               ('literal over', bytes(literal))):
                with self.subTest(cpu=cpu, case=name):
                    k, _, _, main, aux, rest = self.run_mp(cpu, data, 's', 512)
                    self.assertEqual(k, 0)
                    self.assertEqual(main + aux + rest, b'\xee' * 0x6000)
                    k = self.run_mp(cpu, data, 'd', len(data))[0]
                    self.assertEqual(k, 0, 'a draw past the end fails')

    def test_ciderpress_sample_when_at_hand(self):
        sample = cp2_samples.volume().get('/GRAPHICS/ESCHERWATER.MAC')
        if not sample:
            self.skipTest('no CiderPress II samples (tools/cp2_samples.py)')
        data = sample[2]
        for cpu in self.programs:
            ck = self.scan(cpu, data)
            for top in (0, 240, 528):
                with self.subTest(cpu=cpu, top=top):
                    self.draw(cpu, data, ck, top)

    def test_a_file_past_64_kb_is_refused(self):
        # 720 lines of 72 literal bytes each are 52,560 bytes; start the
        # count near the top so that the position passes 65,535
        lines = [bytes([0x5A]) * 72] * 720
        data = bytes(512) + b''.join(bytes([71]) + l for l in lines)
        for cpu in self.programs:
            (self.dir / 'pic.bin').write_bytes(data)
            k, _, _, _, _, _ = self.run_mp(cpu, data, 's', 512)
            self.assertEqual(k, 1)
            padded = bytes(20000) + data
            k, *_ = self.run_mp(cpu, padded, 's', 20512)
            self.assertEqual(k, 0, 'the position would wrap')


if __name__ == '__main__':
    unittest.main()
