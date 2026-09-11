"""Run BLKEDIT's actual write path against every container it accepts.

The point of these tests is the one thing the viewer next door never does:
put bytes back on a disk. They check that a block written and read back
lands at the right offset in every sector order, that the readback really
compares, and that the guards refuse what they are there to refuse.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

SECTORS = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]

HARNESS = PREFIX + r'''
#include "src/plugins/blkedit.c"
static unsigned char lie;            /* the drive reports success and keeps the old bytes */
static long writefail;
static size_t write_data(const void* p, size_t s, size_t n, FILE* f) {
    if (writefail >= 0 && ftell(f) >= writefail) return 0;
    if (lie) return n;               /* accepted, nothing stored */
    return fwrite(p, s, n, f);
}
int main(int argc, char** argv)
{
    static unsigned char scratch[512];
    static struct A2fcApi api;
    unsigned int i;
    a.fread = fread; a.fwrite = write_data; a.fseek = fseek;
    buf = scratch;
    source.file = fopen(argv[1], "r+b");
    source.blocks = atoi(argv[2]);
    source.kind = atoi(argv[3]);
    source.unit = 0;
    source.base = source.kind == 2 ? 64 : 0;
    block = atoi(argv[4]);
    lie = atoi(argv[5]);
    writefail = atol(argv[6]);
    if (!source_read(&source, block, buf)) { printf("readfail\n"); return 0; }
    for (i = 0; i < 512; ++i) buf[i] ^= 0xFF;          /* the "edit" */
    if (!source_write(&source, block, buf)) { printf("writefail\n"); fclose(source.file); return 0; }
    if (!source_read(&source, block, check)) { printf("nocheck\n"); fclose(source.file); return 0; }
    for (i = 0; i < 512 && buf[i] == check[i]; ++i) ;
    printf(i < 512 ? "differs\n" : "identical\n");
    fclose(source.file);
    return 0;
}
'''

BOOT = PREFIX + r'''
#include "src/plugins/blkedit.c"
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    api.cfg_path = argv[2];
    a = api;
    strcpy(source.path, argv[1]);
    source.unit = atoi(argv[3]);
    printf("%u\n", boot_volume());
    return 0;
}
'''


def encode(data, kind):
    """The image as the container stores it, so the test knows where bytes go."""
    if kind == 1:
        out = bytearray(len(data))
        for t in range(len(data) // 4096):
            for s in range(16):
                out[t * 4096 + SECTORS[s] * 256:t * 4096 + (SECTORS[s] + 1) * 256] = \
                    data[t * 4096 + s * 256:t * 4096 + (s + 1) * 256]
        return bytes(out)
    return (bytes(64) if kind == 2 else b'') + bytes(data)


def decode(raw, kind):
    if kind == 2:
        raw = raw[64:]
    if kind != 1:
        return bytes(raw)
    out = bytearray(len(raw))
    for t in range(len(raw) // 4096):
        for s in range(16):
            out[t * 4096 + s * 256:t * 4096 + (s + 1) * 256] = \
                raw[t * 4096 + SECTORS[s] * 256:t * 4096 + (SECTORS[s] + 1) * 256]
    return bytes(out)


class BlkEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='blkedit-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'rw.c').write_text(HARNESS)
        cls.exe = cls.p / 'rw'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'rw.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def edit(self, data, kind, block, lie=0, writefail=-1):
        """Flip every bit of one block through source_write; give back the
        verdict and the whole image, decoded back to plain block order."""
        path = self.p / 'image'
        path.write_bytes(encode(data, kind))
        verdict = subprocess.check_output(
            [str(self.exe), str(path), str(len(data) // 512), str(kind),
             str(block), str(lie), str(writefail)], text=True).strip()
        return verdict, decode(path.read_bytes(), kind)

    def test_a_block_round_trips_in_every_container(self):
        data = bytes(range(256)) * 64                      # 16 KB: 32 blocks, four tracks
        for kind in (0, 1, 2):
            for block in (0, 1, 7, 8, 31):
                with self.subTest(kind=kind, block=block):
                    verdict, image = self.edit(data, kind, block)
                    self.assertEqual(verdict, 'identical')
                    want = bytearray(data)
                    for i in range(block * 512, block * 512 + 512):
                        want[i] ^= 0xFF
                    self.assertEqual(image, bytes(want))

    def test_only_the_named_block_moves(self):
        data = bytes(range(256)) * 64
        for kind in (0, 1, 2):
            verdict, image = self.edit(data, kind, 9)
            self.assertEqual(verdict, 'identical')
            self.assertEqual(image[:9 * 512], data[:9 * 512])
            self.assertEqual(image[10 * 512:], data[10 * 512:])

    def test_a_drive_that_lies_is_caught_by_the_readback(self):
        """Accepting the write and keeping the old bytes must not pass."""
        data = bytes(range(256)) * 64
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                verdict, image = self.edit(data, kind, 3, lie=1)
                self.assertEqual(verdict, 'differs')
                self.assertEqual(image, data)              # nothing was stored

    def test_a_refused_write_is_reported(self):
        data = bytes(range(256)) * 64
        self.assertEqual(self.edit(data, 0, 2, writefail=0)[0], 'writefail')

    def test_a_half_written_dsk_block_is_reported(self):
        """A .DSK block is two sectors: failing on the second is still a
        failure, not a success with half the data."""
        data = bytes(range(256)) * 64
        verdict, image = self.edit(data, 1, 0, writefail=256)
        self.assertEqual(verdict, 'writefail')

    def test_a_block_past_the_end_is_refused(self):
        data = bytes(range(256)) * 4                       # two blocks
        self.assertEqual(self.edit(data, 0, 2)[0], 'readfail')


class BootVolumeGuard(unittest.TestCase):
    """The volume A2FC runs from must be refused; an image file never is."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='blkedit-boot-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'boot.c').write_text(BOOT)
        cls.exe = cls.p / 'boot'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'boot.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def guard(self, volume, cfg, unit=0x60):
        return int(subprocess.check_output(
            [str(self.exe), volume, cfg, str(unit)], text=True))

    def test_the_boot_volume_is_refused(self):
        self.assertEqual(self.guard('/A2FC', '/A2FC/A2FILE/A2FILE.CFG'), 1)

    def test_another_volume_is_allowed(self):
        self.assertEqual(self.guard('/DATA', '/A2FC/A2FILE/A2FILE.CFG'), 0)

    def test_a_longer_name_is_not_a_prefix_match(self):
        """/A2FC must not match /A2FCTEST, nor the other way round."""
        self.assertEqual(self.guard('/A2FC', '/A2FCTEST/A2FILE/A2FILE.CFG'), 0)
        self.assertEqual(self.guard('/A2FCTEST', '/A2FC/A2FILE/A2FILE.CFG'), 0)

    def test_an_image_file_is_never_the_running_program(self):
        self.assertEqual(self.guard('/A2FC', '/A2FC/A2FILE/A2FILE.CFG', unit=0), 0)


if __name__ == '__main__':
    unittest.main()
