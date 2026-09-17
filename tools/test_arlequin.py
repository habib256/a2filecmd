"""Run the Arlequin decoder (src/plugins/arlequin.s) under sim65.

The assembly is what draws the picture: the stream, the header checks, the
placement and the store of every byte. It runs here on both processors,
built with ARL_TEST so that the auxiliary bytes -- written with RAMWRT on,
which sim65 does not have -- land 16 KB higher, at $6000, and the two planes
can be read apart. The reference is tools/arlequin_ref.py, itself checked
against ARLEQUIN's own loader under POM2 (and against the maker's pictures
when /GISTDATA is at hand: A2FC_SAMPLE_DISK).

What arlequin.c adds -- the checking pass before the auxiliary bank is
touched, the /RAM rebuild, the messages -- is bench/arlequin.py's.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import arlequin_ref as ref  # noqa: E402

CFG_START = '$8000'

HARNESS = r'''
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
unsigned char ar_decode(void);
extern unsigned char ar_dry, ar_win;
unsigned char* ar_buf;
static unsigned char buf[255];
static int in, chunk = 255;
unsigned char ar_read(void)
{
    int n = read(in, buf, chunk);
    return n > 0 ? (unsigned char)n : 0;
}
int main(int argc, char** argv)
{
    unsigned char k, r[2];
    ar_buf = buf;
    if (argc > 2) chunk = atoi(argv[2]);
    memset((void*)0x2000, 0xEE, 0x6000);    /* whatever the pages held */
    memset((void*)0x2000, 0, 0x2000);       /* the black arlequin.c lays */
    memset((void*)0x6000, 0, 0x2000);
    ar_dry = argv[1][0] == 'd';
    in = open("pic.bin", O_RDONLY);
    if (in < 0) return 10;
    k = ar_decode();
    r[0] = k; r[1] = ar_win;
    if (write(1, r, 2) != 2) return 11;
    if (write(1, (void*)0x2000, 0x2000) != 0x2000) return 12;   /* main */
    if (write(1, (void*)0x6000, 0x2000) != 0x2000) return 13;   /* aux */
    if (write(1, (void*)0x4000, 0x2000) != 0x2000) return 14;   /* never written */
    return 0;
}
'''


def sample_disk():
    path = os.environ.get('A2FC_SAMPLE_DISK', str(Path.home() / 'src/pom2/hdv/GISTDATA.hdv'))
    return Path(path) if Path(path).exists() else None


class Arlequin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2fc-arlequin-')
        cls.dir = Path(cls.tmp.name)
        target = Path(subprocess.check_output([shutil.which('cl65'), '--print-target-path'],
                                              text=True).strip())
        shutil.copyfile(ROOT / 'src/plugins/arlequin.s', cls.dir / 'arlequin.s')
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
                            '--asm-define', 'ARL_TEST', '-C', str(cls.dir / f'{cpu}.cfg'), '-O',
                            '-o', str(exe), str(cls.dir / 'harness.c'), str(cls.dir / 'arlequin.s')],
                           check=True, cwd=cls.dir)
            cls.programs[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_pic(self, cpu, data, dry=False, chunk=255):
        (self.dir / 'pic.bin').write_bytes(data)
        out = subprocess.run(['sim65', str(self.programs[cpu]), 'd' if dry else 'w', str(chunk)],
                             cwd=self.dir, capture_output=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        o = out.stdout
        return o[0], o[1], o[2:0x2002], o[0x2002:0x4002], o[0x4002:]

    def check(self, cpu, data, chunk=255):
        k, win, main, aux, untouched = self.run_pic(cpu, data, chunk=chunk)
        self.assertEqual(k, 1)
        want_aux, want_main = ref.screen(data)
        self.assertEqual(main, want_main, 'main plane')
        self.assertEqual(aux, want_aux, 'auxiliary plane')
        self.assertEqual(untouched, b'\xee' * 0x2000, 'nothing written past the pages')
        self.assertEqual(bool(win), (data[0], data[1]) != (20, 192))

    def test_synthetic_pictures_on_both_processors(self):
        rng = random.Random(5)
        sizes = [(20, 192), (1, 1), (9, 81), (19, 191), (20, 1), (1, 192), (2, 3)]
        sizes += [(rng.randrange(1, 21), rng.randrange(1, 193)) for _ in range(6)]
        for cpu in self.programs:
            for w, h in sizes:
                with self.subTest(cpu=cpu, size=(w, h)):
                    data = ref.encode(w, ref.random_rows(w, h, rng), rng)
                    self.check(cpu, data, chunk=rng.choice([255, 1, 7, 128]))

    def test_a_run_of_256_and_runs_across_rows(self):
        # $91 then a count of $40: bit 7 kept, and 0 means 256 -- 257 bytes,
        # then 63 literals: the 320 bytes of a 20 x 4 picture
        long = bytes([20, 4]) + ref.SIGNATURE + bytes([0x91, 0x40]) + bytes([0xD5]) * 63
        # 1 x 3 is 12 bytes: one literal and a run of 11 across all three rows
        across = bytes([1, 3]) + ref.SIGNATURE + bytes([0x91, 0x0B])
        for data in (long, across):
            rows, used = ref.decode(data)
            self.assertEqual(used, len(data))
            for cpu in self.programs:
                with self.subTest(cpu=cpu, size=data[:2].hex()):
                    self.check(cpu, data)

    def test_mask_toggles_and_bit7_runs(self):
        data = bytes([2, 1]) + ref.SIGNATURE + bytes([0x00, 0xC5, 0x43, 0x00, 0x03, 0x00, 0x00, 0x81])
        rows, used = ref.decode(data)
        self.assertEqual(used, len(data))
        for cpu in self.programs:
            self.check(cpu, data)

    def test_a_cut_stream_stores_what_came_and_says_so(self):
        rng = random.Random(9)
        data = ref.encode(20, ref.random_rows(20, 192, rng), rng)
        for cpu in self.programs:
            for cut in (4, 5, len(data) // 2, len(data) - 1):
                with self.subTest(cpu=cpu, cut=cut):
                    k, _, main, aux, untouched = self.run_pic(cpu, data[:cut])
                    self.assertEqual(k, 0)
                    self.assertEqual(untouched, b'\xee' * 0x2000)

    def test_a_bad_header_is_refused_before_any_store(self):
        good = ref.encode(3, ref.random_rows(3, 4, random.Random(2)))
        bad = [b'', b'\x14', b'\x14\xc0gs'[:3], b'\x14\xc0gt' + good[4:],
               b'\x00\xc0gs' + good[4:], b'\x15\xc0gs' + good[4:],
               b'\x14\x00gs' + good[4:], b'\x14\xc1gs' + good[4:], b'\x14\xffgs' + good[4:]]
        for cpu in self.programs:
            for data in bad:
                with self.subTest(cpu=cpu, head=data[:4].hex()):
                    k, _, main, aux, untouched = self.run_pic(cpu, data)
                    self.assertEqual(k, 2)
                    self.assertEqual(main + aux, bytes(0x4000))

    def test_a_checking_pass_stores_nothing(self):
        data = ref.encode(20, ref.random_rows(20, 192, random.Random(3)))
        for cpu in self.programs:
            k, _, main, aux, untouched = self.run_pic(cpu, data, dry=True)
            self.assertEqual(k, 1)
            self.assertEqual(main + aux, bytes(0x4000))
            self.assertEqual(untouched, b'\xee' * 0x2000)

    def test_the_makers_pictures_when_the_sample_disk_is_there(self):
        disk = sample_disk()
        if not disk:
            self.skipTest('no /GISTDATA sample disk')
        from prodos_read import Image
        img = Image(disk.read_bytes())
        found = 0

        def walk(key, path):
            for e in img.entries(key):
                name = path + '/' + e[1:1 + (e[0] & 15)].decode('ascii')
                if e[0] >> 4 == 0xD:
                    if not name.startswith('/MUSIC'):
                        yield from walk(int.from_bytes(e[0x11:0x13], 'little'), name)
                elif e[0x10] == 0xF8:
                    yield name, img.read(e)
        for name, data in walk(2, ''):
            if data[2:4] != ref.SIGNATURE:
                continue
            found += 1
            for cpu in self.programs:
                with self.subTest(cpu=cpu, picture=name):
                    self.check(cpu, data)
        self.assertGreater(found, 0, 'the sample disk has Arlequin pictures')


if __name__ == '__main__':
    unittest.main()
