"""DiskCopy 4.2 in IMGCONV: the checksum under sim65, the conversions on the host.

src/plugins/imgconv.s adds a block to the DiskCopy checksum; it runs under
sim65 on both processors against tools/dc42.py. IMGCONV's real entry point
(the harness of test_imgconv_safety.py; imgconv.c carries the C twin of
that routine for host builds) converts to and from DiskCopy; every result is compared with the
reference, byte for byte, and a DiskCopy source that does not match its
own checksum is refused before anything is written. The resident's side --
a .DC opened as a folder -- is bench/diskcopy.py's.
"""
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dc42  # noqa: E402
import cp2_samples  # noqa: E402
from po2dsk import SECTORS  # noqa: E402
from test_imgconv_safety import HARNESS as SAFETY  # noqa: E402
from test_six_plugins import ROOT  # noqa: E402

HOST = SAFETY.replace(
    'plugin_entry(&api);puts(note);return 0;',
    'plugin_entry(&api);printf("%s\\n%02X %04X\\n",note,type,aux);return 0;')

SIM = r'''
#include <fcntl.h>
#include <unistd.h>
extern unsigned long dc_sum;
void __fastcall__ dc_add(const unsigned char* p);
static unsigned char block[512];
int main(void)
{
    int in = open("blocks.bin", O_RDONLY);
    dc_sum = 0;
    while (read(in, block, 512) == 512) {
        dc_add(block);
        dc_add(block + 256);
    }
    write(1, &dc_sum, 4);
    return 0;
}
'''


def to_dsk(po):
    """DOS 3.3 order for any whole number of tracks (po2dsk.py does 35)."""
    out = bytearray(len(po))
    for b in range(len(po) // 512):
        track, pair = divmod(b, 8)
        for half, sector in enumerate(SECTORS[pair]):
            o = (track * 16 + sector) * 256
            out[o:o + 256] = po[b * 512 + half * 256:b * 512 + (half + 1) * 256]
    return bytes(out)


def volume(blocks, seed):
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(blocks * 512))


class DiskCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dc42-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'host.c').write_text(HOST)
        cls.exe = cls.root / 'host'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.root / 'host.c'), '-o', str(cls.exe)], check=True,
                       capture_output=True)
        cls.v800 = volume(1600, 1)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def convert(self, name, data, key, fault=0):
        case = Path(tempfile.mkdtemp(dir=self.root))
        (case / 'S').mkdir()
        (case / 'D').mkdir()
        (case / 'S' / name).write_bytes(data)
        out = subprocess.run([str(self.exe), str(case / 'S'), str(case / 'D'), str(fault), key,
                              name, str(len(data))], capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        note, types = out.stdout.splitlines()[:2]
        made = {p.name: p.read_bytes() for p in (case / 'D').iterdir()}
        self.assertEqual((case / 'S' / name).read_bytes(), data, 'the source is untouched')
        return note, types, made

    def test_checksum_under_sim65(self):
        data = volume(64, 2) + bytes(512) + b'\xff' * 512
        (self.root / 'blocks.bin').write_bytes(data)
        shutil.copyfile(ROOT / 'src/plugins/imgconv.s', self.root / 'imgconv.s')
        (self.root / 'sim.c').write_text(SIM)
        for cpu in ('sim6502', 'sim65c02'):
            exe = self.root / cpu
            subprocess.run(['cl65', '-t', cpu, '-O', '-o', str(exe), str(self.root / 'sim.c'),
                            str(self.root / 'imgconv.s')], check=True, cwd=self.root,
                           capture_output=True)
            out = subprocess.run(['sim65', str(exe)], cwd=self.root, capture_output=True,
                                 timeout=120)
            self.assertEqual(int.from_bytes(out.stdout, 'little'), dc42.checksum(data), cpu)

    def test_to_diskcopy(self):
        note, types, made = self.convert('DISK.PO', self.v800, 'C')
        self.assertEqual(made, {'DISK.DC': dc42.wrap(self.v800, b'DISK.DC')}, note)
        self.assertEqual(types, 'E0 8005')
        # from DOS order and from a 2IMG: the same blocks
        note, types, made = self.convert('DISK.DSK', to_dsk(self.v800), 'C')
        self.assertEqual(made, {'DISK.DC': dc42.wrap(self.v800, b'DISK.DC')}, note)
        for blocks in (800, 1440, 2880):
            data = volume(blocks, blocks)
            note, types, made = self.convert('X.PO', data, 'c')
            self.assertEqual(made, {'X.DC': dc42.wrap(data, b'X.DC')}, note)

    def test_from_diskcopy(self):
        dc = dc42.wrap(self.v800, b'Some disk')
        for name in ('DISK.DC', 'DISK.DC42', 'DISK.IMAGE', 'DISK.IMG'):
            note, types, made = self.convert(name, dc, 'P')
            self.assertEqual(made, {'DISK.PO': self.v800}, (name, note))
            self.assertEqual(types, '06 0000')
        note, types, made = self.convert('DISK.DC', dc, 'D')
        self.assertEqual(made, {'DISK.DSK': to_dsk(self.v800)}, note)
        note, types, made = self.convert('DISK.DC', dc, '2')
        self.assertEqual(made['DISK.2MG'][64:], self.v800, note)
        # tag bytes after the blocks are left behind
        tags = dc[:0x44] + (19200).to_bytes(4, 'big') + dc[0x48:] + bytes(19200)
        note, types, made = self.convert('TAGS.DC', tags, 'P')
        self.assertEqual(made, {'TAGS.PO': self.v800}, note)

    def test_refusals_write_nothing(self):
        dc = dc42.wrap(self.v800)
        cases = [
            ('bad checksum', dc[:0x4B] + bytes([dc[0x4B] ^ 1]) + dc[0x4C:], 'P',
             'DiskCopy checksum mismatch: nothing written.'),
            ('one block changed', dc[:84 + 700 * 512] + b'\x00' * 512 + dc[84 + 701 * 512:], 'P',
             'DiskCopy checksum mismatch: nothing written.'),
            ('no signature', dc[:0x52] + b'\x00\x01' + dc[0x54:], 'P', 'Not a DiskCopy 4.2 image.'),
            ('long name', b'\x40' + dc[1:], 'P', 'Not a DiskCopy 4.2 image.'),
            ('short file', dc[:-512], 'P', 'Not a DiskCopy 4.2 image.'),
            ('odd size', dc[:0x43] + b'\x01' + dc[0x44:], 'P', 'Not a DiskCopy 4.2 image.'),
        ]
        for what, data, key, want in cases:
            with self.subTest(what):
                note, types, made = self.convert('BAD.DC', data, key)
                self.assertEqual(note, want)
                self.assertEqual(made, {})
        note, types, made = self.convert('SMALL.PO', bytes(280 * 512), 'C')
        self.assertEqual((note, made), ('DiskCopy holds 400K, 800K, 720K or 1440K.', {}))

    def test_a_real_image(self):
        real = cp2_samples.path('diskcopy/Installer Disk 1.image')
        if not real:
            self.skipTest('no CiderPress II DiskCopy sample (tools/cp2_samples.py)')
        data = real.read_bytes()
        note, types, made = self.convert('INSTALL.IMAGE', data, 'P')
        self.assertEqual(made, {'INSTALL.PO': dc42.unwrap(data)}, note)


if __name__ == '__main__':
    unittest.main()
