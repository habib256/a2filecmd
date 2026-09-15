"""Run BLKEDIT's actual write path against every container it accepts.

The point of these tests is the one thing the viewer next door never does:
put bytes back on a disk. They check that a block written and read back
lands at the right offset in every sector order, that the readback really
compares, and that the guards refuse what they are there to refuse.

The image is opened by the real image_open, as the overlay does: cc65's
fopen("rb") is O_RDONLY, so a harness that opened the file itself for
update would hide an editor that can never write. The stream mock keeps
cc65's rule that fread and fwrite refuse a stream whose error flag is set.
"""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

SECTORS = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]
NAMES = {0: 'IMAGE.PO', 1: 'IMAGE.DSK', 2: 'IMAGE.2MG'}

HARNESS = PREFIX + r'''
static void mock_clearerr(FILE*);
#define clearerr mock_clearerr
#include "src/plugins/blkedit.c"
#undef clearerr
static unsigned char lie;            /* the drive reports success and keeps the old bytes */
static long writefail;
static unsigned char errflag;        /* cc65's _FERROR, which host stdio does not honour */
static const char* host_image;
static char opened_mode[4];
static struct DirEntry entry;
static unsigned char listed;
static void mock_clearerr(FILE* f) { (void)f; errflag = 0; }
static FILE* open_image(const char* path, const char* mode) {
    (void)path; strcpy(opened_mode, mode); return fopen(host_image, mode);
}
static size_t read_data(void* p, size_t s, size_t n, FILE* f) {
    size_t r;
    if (errflag) return 0;
    r = fread(p, s, n, f);
    if (r != n) errflag = 1;
    return r;
}
static size_t write_data(const void* p, size_t s, size_t n, FILE* f) {
    size_t r;
    if (errflag) return 0;
    if (writefail >= 0 && ftell(f) >= writefail) { errflag = 1; return 0; }
    if (lie) return n;               /* accepted, nothing stored */
    r = fwrite(p, s, n, f);
    if (r != n) errflag = 1;
    return r;
}
static unsigned char dir_open(const char* path) { (void)path; listed = 0; return 1; }
static unsigned char dir_next(void) { return !listed++; }
static void dir_close(void) {}
int main(int argc, char** argv)
{
    static unsigned char scratch[512];
    static unsigned char original[512];
    unsigned int i;
    FILE* f;
    host_image = argv[1];
    a.fread = read_data; a.fwrite = write_data; a.fseek = fseek;
    a.fopen = open_image; a.fclose = fclose;
    a.dir_open = dir_open; a.dir_next = dir_next; a.dir_close = dir_close;
    a.dir_entry = &entry;
    a.strcpy = strcpy; a.strcmp = strcmp; a.strlen = strlen;
    buf = scratch;
    f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); entry.size = ftell(f); fclose(f);
    strcpy(entry.name, argv[2]);
    sprintf(source.path, "/H/%s", argv[2]);
    block = atoi(argv[3]);
    lie = atoi(argv[4]);
    writefail = atol(argv[5]);
    if (!image_open(&source)) { printf("openfail\n"); return 0; }
    if (!source_read(&source, block, buf)) { printf("readfail %s\n", opened_mode); return 0; }
    memcpy(original, buf, 512);
    for (i = 0; i < 512; ++i) buf[i] ^= 0xFF;          /* the "edit" */
    if (!source_write(&source, block, buf)) {
        /* The session goes on: the block must still read, and it must
         * still hold what it held. */
        writefail = -1;
        printf("writefail %s %s\n", opened_mode,
               source_read(&source, block, check) && !memcmp(check, original, 512) ? "readable" : "unreadable");
        source_close(&source); return 0;
    }
    if (!source_read(&source, block, check)) { printf("nocheck %s\n", opened_mode); source_close(&source); return 0; }
    for (i = 0; i < 512 && buf[i] == check[i]; ++i) ;
    printf(i < 512 ? "differs %s\n" : "identical %s\n", opened_mode);
    source_close(&source);
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
    if kind == 2:
        header = bytearray(64)
        header[0:4] = b'2IMG'
        header[8:10] = (64).to_bytes(2, 'little')          # header length
        header[10:12] = (1).to_bytes(2, 'little')          # version
        header[12:16] = (1).to_bytes(4, 'little')          # ProDOS order
        header[20:24] = (len(data) // 512).to_bytes(4, 'little')
        header[24:28] = (64).to_bytes(4, 'little')         # data offset
        header[28:32] = len(data).to_bytes(4, 'little')
        return bytes(header) + bytes(data)
    return bytes(data)


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

    def edit(self, data, kind, block, lie=0, writefail=-1, locked=False):
        """Flip every bit of one block through source_write; give back the
        verdict and the whole image, decoded back to plain block order."""
        path = self.p / 'image'
        if path.exists():
            path.chmod(0o644)
        path.write_bytes(encode(data, kind))
        if locked:
            path.chmod(stat.S_IRUSR | stat.S_IRGRP)
        try:
            verdict = subprocess.check_output(
                [str(self.exe), str(path), NAMES[kind], str(block), str(lie), str(writefail)],
                text=True).strip()
        finally:
            path.chmod(0o644)
        return verdict, decode(path.read_bytes(), kind)

    def test_a_block_round_trips_in_every_container(self):
        data = bytes(range(256)) * 64                      # 16 KB: 32 blocks, four tracks
        for kind in (0, 1, 2):
            for block in (0, 1, 7, 8, 31):
                with self.subTest(kind=kind, block=block):
                    verdict, image = self.edit(data, kind, block)
                    self.assertEqual(verdict, 'identical r+b')
                    want = bytearray(data)
                    for i in range(block * 512, block * 512 + 512):
                        want[i] ^= 0xFF
                    self.assertEqual(image, bytes(want))

    def test_only_the_named_block_moves(self):
        data = bytes(range(256)) * 64
        for kind in (0, 1, 2):
            verdict, image = self.edit(data, kind, 9)
            self.assertEqual(verdict, 'identical r+b')
            self.assertEqual(image[:9 * 512], data[:9 * 512])
            self.assertEqual(image[10 * 512:], data[10 * 512:])

    def test_a_drive_that_lies_is_caught_by_the_readback(self):
        """Accepting the write and keeping the old bytes must not pass."""
        data = bytes(range(256)) * 64
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                verdict, image = self.edit(data, kind, 3, lie=1)
                self.assertEqual(verdict, 'differs r+b')
                self.assertEqual(image, data)              # nothing was stored

    def test_a_refused_write_is_reported_and_the_session_can_still_read(self):
        """A failed write sets the stream's error flag; cc65's fread then
        refuses everything until it is cleared."""
        data = bytes(range(256)) * 64
        for kind in (0, 2):
            with self.subTest(kind=kind):
                verdict, image = self.edit(data, kind, 2, writefail=0)
                self.assertEqual(verdict, 'writefail r+b readable')
                self.assertEqual(image, data)

    def test_a_half_written_dsk_block_is_reported(self):
        """A .DSK block is two sectors: failing on the second is still a
        failure, not a success with half the data."""
        data = bytes(range(256)) * 64
        verdict, image = self.edit(data, 1, 0, writefail=256)
        self.assertTrue(verdict.startswith('writefail r+b'), verdict)

    def test_a_locked_image_opens_read_only_and_is_never_written(self):
        data = bytes(range(256)) * 64
        if os.geteuid() == 0:
            self.skipTest('root ignores the read-only permission')
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                verdict, image = self.edit(data, kind, 5, locked=True)
                self.assertEqual(verdict, 'writefail rb readable')
                self.assertEqual(image, data)

    def test_a_block_past_the_end_is_refused(self):
        data = bytes(range(256)) * 4                       # two blocks
        self.assertEqual(self.edit(data, 0, 2)[0], 'readfail r+b')


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

    def test_a_subdirectory_panel_still_names_its_volume(self):
        """BLKEDIT takes the panel path: /A2FC/GAMES is the running volume."""
        self.assertEqual(self.guard('/A2FC/GAMES', '/A2FC/A2FILE/A2FILE.CFG'), 1)
        self.assertEqual(self.guard('/A2FC/A2FILE', '/A2FC/A2FILE/A2FILE.CFG'), 1)
        self.assertEqual(self.guard('/DATA/A2FC', '/A2FC/A2FILE/A2FILE.CFG'), 0)
        self.assertEqual(self.guard('/A2FCTEST/GAMES', '/A2FC/A2FILE/A2FILE.CFG'), 0)
        self.assertEqual(self.guard('/A2FC/GAMES', '/A2FCTEST/A2FILE/A2FILE.CFG'), 0)

    def test_an_image_file_is_never_the_running_program(self):
        self.assertEqual(self.guard('/A2FC', '/A2FC/A2FILE/A2FILE.CFG', unit=0), 0)


if __name__ == '__main__':
    unittest.main()
