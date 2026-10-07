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


# The whole overlay, entry point and key loop, on a mock drive whose disk
# the script can change. argv: the disks file (DISKS blocks of 512 bytes
# each, one after the other), then the script: the keys, '!' for ESC, and
# '@X' to put disk X in the drive before the next key, prompt or question
# ('@E' is disk A with a block 2 that no longer reads). The ERASE prompt
# always answers ERASE: what is tested is what happens after it.
DEVICE = PREFIX + r'''
#include <stdarg.h>
#include "src/plugins/blkedit.c"
#define NB 16
#define DISKS 4
static unsigned char disks[DISKS][NB * 512];
static int drive;                    /* the disk in the drive */
static unsigned char bad2;           /* its block 2 does not read */
static const char* script;
static char input[18], notes[80], full[90], said[65536];
static unsigned int writes, reads;
static int twin;                     /* ON_LINE lists the drive's volume twice */
static void events(void) {
    while (*script == '@') {
        drive = script[1] == 'E' ? 0 : script[1] - 'A';
        bad2 = script[1] == 'E';
        script += 2;
    }
}
static unsigned char mock(unsigned char cmd, void* p) {
    struct Block* b = p;
    if (cmd == 0xC5) {
        struct Online* o = p;
        unsigned char* h = disks[drive] + 1024;
        memset(o->buffer, 0, 256);
        o->buffer[0] = 0x60 | (h[4] & 15);
        memcpy(o->buffer + 1, h + 5, h[4] & 15);
        if (twin) { o->buffer[16] = 0xE0 | (h[4] & 15); memcpy(o->buffer + 17, h + 5, h[4] & 15); }
        return 0;
    }
    if (b->unit != 0x60 || b->block >= NB) return 0x27;
    if (cmd == 0x80) ++reads;
    if (cmd == 0x80) {
        if (bad2 && b->block == 2) return 0x27;
        memcpy(b->buffer, disks[drive] + b->block * 512, 512);
        return 0;
    }
    if (cmd == 0x81) {
        ++writes;
        memcpy(disks[drive] + b->block * 512, b->buffer, 512);
        return 0;
    }
    abort();
}
static void say(const char* s) {
    if (strlen(said) + strlen(s) + 2 < sizeof said) { strcat(said, s); strcat(said, "\n"); }
}
static char key(void) { char c; events(); c = *script ? *script++ : '!'; return c == '!' ? KEY_ESC : c; }
static unsigned char ask(const char* q, const char* d, unsigned char n) {
    (void)q; (void)d; (void)n; events(); strcpy(input, "ERASE"); return 1;
}
static unsigned char yes(const char* q) { (void)q; events(); return 1; }
static int out(const char* f, ...) {
    char line[256];
    va_list ap;
    if (!strcmp(f, "%02X") || !strcmp(f, "%02X ") || !strcmp(f, "%03X  ")) return 0;
    va_start(ap, f); vsnprintf(line, sizeof line, f, ap); va_end(ap);
    say(line);
    return 0;
}
static void puts_(const char* s) { (void)s; }
static void putc_(char c) { (void)c; }
static void xy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static unsigned char rev(unsigned char r) { (void)r; return 0; }
static void cls(void) {}
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    FILE* f = fopen(argv[1], "rb");
    if (!f || fread(disks, 1, sizeof disks, f) != sizeof disks) abort();
    fclose(f);
    script = argv[2];
    strcpy(selected.name, "/DISKA");
    selected.mdate = 6;
    /* argv[3]: "path" opens /DISKA from a panel path, "twin" too with a
     * second /DISKA on line (unit $E0). Otherwise the volume-list row. */
    if (argc > 3) { strcpy(panels[0].path, "/DISKA"); twin = !strcmp(argv[3], "twin"); }
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = notes; api.input = input; api.full = full;
    api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.mli = mock; api.cgetc = key; api.prompt = ask; api.confirm = yes; api.sprintf = sprintf;
    api.message = say; api.cprintf = out; api.cputs = puts_; api.cputc = putc_;
    api.gotoxy = xy; api.revers = rev; api.clrscr = cls;
    plugin_entry(&api);
    f = fopen(argv[1], "wb"); fwrite(disks, 1, sizeof disks, f); fclose(f);
    printf("%u writes\n%s\n%s", writes, notes, said);
    return 0;
}
'''

# The whole overlay on an IMAGE FILE (the panel inside /H, the image
# selected), through the real image_open: argv the host image, its name,
# the key script ('!' is ESC; the ERASE prompt answers ERASE).
IMAGE = PREFIX + r'''
#include <stdarg.h>
static void mock_clearerr(FILE*);
#define clearerr mock_clearerr
#include "src/plugins/blkedit.c"
#undef clearerr
static unsigned char errflag;
static const char* host_image;
static const char* script;
static struct DirEntry entry;
static unsigned char listed;
static char input[18], notes[80], full[90], said[8192];
static void mock_clearerr(FILE* f) { (void)f; errflag = 0; }
static FILE* open_image(const char* path, const char* mode) { (void)path; return fopen(host_image, mode); }
static size_t read_data(void* p, size_t s, size_t n, FILE* f) {
    size_t r; if (errflag) return 0; r = fread(p, s, n, f); if (r != n) errflag = 1; return r;
}
static size_t write_data(const void* p, size_t s, size_t n, FILE* f) {
    size_t r; if (errflag) return 0; r = fwrite(p, s, n, f); if (r != n) errflag = 1; return r;
}
static unsigned char dir_open(const char* path) { (void)path; listed = 0; return 1; }
static unsigned char dir_next(void) { return !listed++; }
static void dir_close(void) {}
static void say(const char* s) {
    if (strlen(said) + strlen(s) + 2 < sizeof said) { strcat(said, s); strcat(said, "\n"); }
}
static char key(void) { char c = *script ? *script++ : '!'; return c == '!' ? KEY_ESC : c; }
static unsigned char ask(const char* q, const char* d, unsigned char n) {
    (void)q; (void)d; (void)n; strcpy(input, "ERASE"); return 1;
}
static unsigned char yes(const char* q) { (void)q; return 1; }
static int out(const char* f, ...) {
    char line[256]; va_list ap;
    if (!strcmp(f, "%02X") || !strcmp(f, "%02X ") || !strcmp(f, "%03X  ")) return 0;
    va_start(ap, f); vsnprintf(line, sizeof line, f, ap); va_end(ap);
    say(line); return 0;
}
static void puts_(const char* s) { (void)s; }
static void putc_(char c) { (void)c; }
static void xy(unsigned char x, unsigned char y) { (void)x; (void)y; }
static unsigned char rev(unsigned char r) { (void)r; return 0; }
static void cls(void) {}
static unsigned char nomli(unsigned char cmd, void* p) { (void)cmd; (void)p; abort(); }
int main(int argc, char** argv)
{
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    FILE* f;
    (void)argc;
    host_image = argv[1];
    f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); entry.size = ftell(f); fclose(f);
    strcpy(entry.name, argv[2]); strcpy(selected.name, argv[2]); selected.access = 0xC3;
    script = argv[3];
    strcpy(panels[0].path, "/H"); sprintf(full, "/H/%s", argv[2]);
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = notes; api.input = input; api.full = full;
    api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.mli = nomli; api.cgetc = key; api.prompt = ask; api.confirm = yes;
    api.message = say; api.cprintf = out; api.cputs = puts_; api.cputc = putc_;
    api.gotoxy = xy; api.revers = rev; api.clrscr = cls;
    api.fread = read_data; api.fwrite = write_data; api.fseek = fseek;
    api.fopen = open_image; api.fclose = fclose;
    api.dir_open = dir_open; api.dir_next = dir_next; api.dir_close = dir_close;
    api.dir_entry = &entry;
    plugin_entry(&api);
    printf("%s\n%s", notes, said);
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

    def edit(self, data, kind, block, lie=0, writefail=-1, locked=False, protect=False):
        """Flip every bit of one block through source_write; give back the
        verdict and the whole image, decoded back to plain block order."""
        path = self.p / 'image'
        if path.exists():
            path.chmod(0o644)
        raw = bytearray(encode(data, kind))
        if protect:
            raw[0x13] |= 0x80                  # 2IMG flags, bit 31: write protected
        path.write_bytes(bytes(raw))
        self.stored = bytes(raw)
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

    def test_a_write_protected_2mg_is_never_written(self):
        """The container's own write protection is bit 31 of its flags, the
        top bit of header byte 19. Measured before image_open looked at it:
        the file opened for update, the block was written and read back --
        "identical r+b" -- on a disk whose owner had said not to. The file
        still opens r+b (ProDOS would let it); every write is refused, the
        block still reads, and not one byte of the file moves, the header
        included."""
        data = bytes(range(256)) * 64
        for block in (0, 5, 31):
            with self.subTest(block=block):
                verdict, image = self.edit(data, 2, block, protect=True)
                self.assertEqual(verdict, 'writefail r+b readable')
                self.assertEqual(image, data)
                self.assertEqual((self.p / 'image').read_bytes(), self.stored)
        # the other bits of that byte are not a lock
        verdict, image = self.edit(data, 2, 5)
        self.assertEqual(verdict, 'identical r+b')

    def test_a_block_past_the_end_is_refused(self):
        data = bytes(range(256)) * 4                       # two blocks
        self.assertEqual(self.edit(data, 0, 2)[0], 'readfail r+b')


class SmallImage(unittest.TestCase):
    """An image of one or two blocks has no block 2.

    Before (bk/mk.py, 2026-10-07): the identity read block 2 on the first
    pass, failed, and BLKEDIT closed with "Block read failed." on a 1- or
    2-block .PO -- a regression of the wrong-disk guard, since image_open
    accepts any count from 1. Now block 0 is the identity of such an image,
    and the edit lands."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='blkedit-small-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'img.c').write_text(IMAGE)
        cls.exe = cls.p / 'img'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'img.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_image(self, data, script, name='IMAGE.PO'):
        path = self.p / name
        path.write_bytes(data)
        out = subprocess.check_output([str(self.exe), str(path), name, script], text=True)
        return out, path.read_bytes()

    def test_one_and_two_block_images_open_and_take_an_edit(self):
        for n in (1, 2):
            for block, script in ((0, 'ABWx!'), (n - 1, 'N' * (n - 1) + 'ABWx!')):
                with self.subTest(blocks=n, block=block):
                    data = bytes((i * 7 + n) & 255 for i in range(512 * n))
                    out, after = self.run_image(data, script)
                    self.assertNotIn('Block read failed', out)
                    self.assertIn('Block %u written and read back identical' % block, out)
                    want = bytearray(data); want[block * 512] = 0xAB
                    self.assertEqual(after, bytes(want))

    def test_block_0_of_a_small_image_written_twice(self):
        """Block 0 is the identity there: writing it renews it, as block 2
        does on a bigger disk."""
        data = bytes(512)
        out, after = self.run_image(data, 'ABWxCDWx!')
        self.assertEqual(out.count('read back identical'), 2)
        self.assertEqual(after[:2], bytes([0xAB, 0xCD]))
        self.assertEqual(after[2:], data[2:])

    def test_a_three_block_image_still_signs_block_2(self):
        data = bytes((i * 3) & 255 for i in range(1536))
        out, after = self.run_image(data, 'NNABWx!')
        self.assertIn('Block 2 written and read back identical', out)
        self.assertEqual(after[1024], 0xAB)


def volume(name, seed, header_from=None, block2_from=None):
    """A sixteen-block ProDOS volume whose every byte depends on `seed`.
    `header_from` keeps another volume's block 2 bytes 0-42 (links and the
    whole volume header: same name, dates, size); `block2_from` its whole
    block 2."""
    data = bytearray((i * (2 * seed + 1) + seed * 37 + i // 512) & 255 for i in range(16 * 512))
    h = bytearray(data[1024:1536])
    h[0:4] = bytes([0, 0, 3, 0])
    h[4] = 0xF0 | len(name)
    h[5:5 + 15] = name.encode().ljust(15, b'\0')
    h[35], h[36] = 39, 13
    h[39:41] = (6).to_bytes(2, 'little')
    h[41:43] = (16).to_bytes(2, 'little')
    data[1024:1536] = h
    if header_from is not None:
        data[1024:1024 + 43] = header_from[1024:1024 + 43]
    if block2_from is not None:
        data[1024:1536] = block2_from[1024:1536]
    return bytes(data)


class WrongDisk(unittest.TestCase):
    """W writes to the disk OPENED, never to whatever is in the drive.

    Before the fix (measured 2026-10-06 on 535682e with this harness), the
    disk swapped in during the ERASE prompt received the block: script
    NNNNNABW@B, disk B's block 5 became disk A's block 5 with byte 0 = $AB,
    1 write, and the read-back from B matched, so 'Block 5 written and read
    back identical' was reported. Same with disk C, which carries disk A's
    volume header byte for byte (same name, dates, size) but other
    directory entries in block 2. With block 2 unreadable the write went
    through all the same. Writing block 2 (script NNABWxCDW@B) put disk
    A's edited volume header over disk B's: B was renamed DISKA.

    The identity is block 2 as read when the disk was opened, its CRC-32
    (since 2026-10-07; before, two pairs of 8-bit running sums that the
    shapes of test_signature_collisions_of_the_running_sums_are_refused
    went through). A copy whose block 2 is identical byte for byte cannot
    be told apart at all (test_an_exact_copy_of_block_2_is_not_detected)."""

    A = volume('DISKA', 1)
    B = volume('DISKB', 2)
    C = volume('DISKA', 3, header_from=A)
    D = volume('DISKA', 4, block2_from=A)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='blkedit-swap-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'dev.c').write_text(DEVICE)
        cls.exe = cls.p / 'dev'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'dev.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_script(self, script):
        path = self.p / 'disks'
        path.write_bytes(self.A + self.B + self.C + self.D)
        out = subprocess.check_output([str(self.exe), str(path), script], text=True)
        raw = path.read_bytes()
        disks = [raw[i * 8192:(i + 1) * 8192] for i in range(4)]
        return int(out.split()[0]), out, disks

    @staticmethod
    def edited(disk, block, byte=0xAB):
        d = bytearray(disk)
        d[block * 512] = byte
        return bytes(d)

    def test_the_opened_disk_is_written_when_it_stays(self):
        writes, out, disks = self.run_script('NNNNNABWx!')
        self.assertEqual(writes, 1)
        self.assertEqual(disks[0], self.edited(self.A, 5))
        self.assertEqual(disks[1:], [self.B, self.C, self.D])
        self.assertIn('Block 5 written and read back identical', out)

    def test_another_volume_swapped_in_during_the_prompt_is_not_written(self):
        writes, out, disks = self.run_script('NNNNNABW@Bx!')
        self.assertEqual(writes, 0)
        self.assertEqual(disks, [self.A, self.B, self.C, self.D])
        self.assertIn('NOT WRITTEN: NOT /DISKA AS OPENED', out)
        self.assertNotIn('read back identical', out)

    def test_the_same_name_with_other_contents_is_not_written(self):
        """Disk C: disk A's volume header byte for byte, other entries."""
        writes, out, disks = self.run_script('NNNNNABW@Cx!')
        self.assertEqual(writes, 0)
        self.assertEqual(disks, [self.A, self.B, self.C, self.D])
        self.assertIn('NOT WRITTEN: NOT /DISKA AS OPENED', out)

    def test_one_changed_header_byte_is_enough(self):
        """Every byte of block 2 counts, one at a time: a disk that
        differs from A by a single byte anywhere in block 2 is refused."""
        for off in (0, 4, 9, 41, 42, 43, 255, 256, 300, 511):
            for delta in (1, 0x80, 0xFF):
                with self.subTest(off=off, delta=delta):
                    d = bytearray(self.A)
                    d[1024 + off] = (d[1024 + off] + delta) & 255
                    path = self.p / 'disks'
                    path.write_bytes(self.A + bytes(d) + self.C + self.D)
                    out = subprocess.check_output([str(self.exe), str(path), 'NNNNNABW@Bx!'], text=True)
                    raw = path.read_bytes()
                    self.assertTrue(out.startswith('0 writes'), out[:40])
                    self.assertEqual(raw[:8192], self.A)
                    self.assertEqual(raw[8192:16384], bytes(d))

    def test_a_swap_before_w_is_caught_too(self):
        """The disk changed while the block was being edited, not during
        the prompt: the check is still made after the prompt."""
        writes, out, disks = self.run_script('NNNNNAB@BWx!')
        self.assertEqual(writes, 0)
        self.assertEqual(disks, [self.A, self.B, self.C, self.D])

    def test_an_unreadable_block_2_refuses(self):
        writes, out, disks = self.run_script('NNNNNABW@Ex!')
        self.assertEqual(writes, 0)
        self.assertEqual(disks, [self.A, self.B, self.C, self.D])
        self.assertIn('NOT WRITTEN: NOT /DISKA AS OPENED', out)

    def test_the_edit_survives_and_lands_once_the_right_disk_is_back(self):
        writes, out, disks = self.run_script('NNNNNABW@Bx@AWx!')
        self.assertEqual(writes, 1)
        self.assertEqual(disks[0], self.edited(self.A, 5))
        self.assertEqual(disks[1:], [self.B, self.C, self.D])
        self.assertIn('Block 5 written and read back identical', out)

    def test_block_2_itself_can_be_written_twice(self):
        """Writing block 2 changes the identity: the second write of the
        session must compare with what the first one left."""
        writes, out, disks = self.run_script('NNABWxCDWx!')
        self.assertEqual(writes, 2)
        want = bytearray(self.A)
        want[1024], want[1025] = 0xAB, 0xCD
        self.assertEqual(disks[0], bytes(want))
        self.assertEqual(disks[1:], [self.B, self.C, self.D])

    def test_block_2_written_then_swapped_is_still_refused(self):
        writes, out, disks = self.run_script('NNABWxCDW@Bx!')
        self.assertEqual(writes, 1)
        self.assertEqual(disks[0], self.edited(self.A, 2))
        self.assertEqual(disks[1:], [self.B, self.C, self.D])

    def run_disks(self, disks, script, *mode):
        path = self.p / 'disks'
        path.write_bytes(b''.join(disks))
        out = subprocess.check_output([str(self.exe), str(path), script] + list(mode), text=True)
        raw = path.read_bytes()
        return int(out.split()[0]), out, [raw[i * 8192:(i + 1) * 8192] for i in range(4)]

    @staticmethod
    def with_block2(disk, b2):
        d = bytearray(disk)
        d[1024:1536] = b2
        return bytes(d)

    def collision_shapes(self):
        """Block 2 of disk A, then a disk that differs from it only in its
        block 2, in each way the former signature (two pairs of 8-bit running
        sums per half) could not see -- bug-hunt probe bk/coll.py."""
        a2 = bytearray(self.A[1024:1536])
        shapes = []
        c = bytearray(a2); c[100] ^= 0x80; c[102] ^= 0x80
        shapes.append(('bit 7 of two bytes an even distance apart', a2, c))
        i = 60
        while (a2[i] - a2[i + 128]) % 2 or a2[i] == a2[i + 128]:
            i += 1
        c = bytearray(a2); c[i], c[i + 128] = c[i + 128], c[i]
        shapes.append(('two bytes 128 apart swapped', a2, c))
        base = bytearray(a2); e1, e3 = 4 + 39, 4 + 39 * 3
        base[e3 + 38] = (base[e3 + 38] + sum(base[e1:e1 + 39]) - sum(base[e3:e3 + 39])) & 255
        c = bytearray(base); c[e1:e1 + 39], c[e3:e3 + 39] = base[e3:e3 + 39], base[e1:e1 + 39]
        shapes.append(('entries 1 and 3 of equal byte sums swapped', base, c))
        return shapes

    @staticmethod
    def old_signature(b2):
        s = t = u = v = 0
        for i in range(256):
            s = (s + b2[i]) & 255; t = (t + s) & 255
            u = (u + b2[256 + i]) & 255; v = (v + u) & 255
        return s, t, u, v

    def test_signature_collisions_of_the_running_sums_are_refused(self):
        """Before: each of these disks, swapped in at the ERASE prompt,
        passed the 32-bit running-sum identity and received disk A's block 5
        (1 write, "read back identical"). The CRC-32 tells every one apart."""
        for name, a2, c2 in self.collision_shapes():
            with self.subTest(name):
                self.assertNotEqual(a2, c2)
                self.assertEqual(self.old_signature(a2), self.old_signature(c2))
                a, c = self.with_block2(self.A, a2), self.with_block2(self.C, c2)
                writes, out, disks = self.run_disks([a, self.B, c, self.D], 'NNNNNABW@Cx!')
                self.assertEqual(writes, 0, out)
                self.assertEqual(disks, [a, self.B, c, self.D])
                self.assertIn('NOT WRITTEN: NOT /DISKA AS OPENED', out)

    def test_a_panel_path_on_one_volume_is_written(self):
        writes, out, disks = self.run_disks([self.A, self.B, self.C, self.D], 'NNNNNABWx!', 'path')
        self.assertEqual(writes, 1)
        self.assertEqual(disks[0], self.edited(self.A, 5))

    def test_two_volumes_of_the_name_refuse_a_panel_path(self):
        """Before: two drives named /DISKA, the panel inside /DISKA: unit_of
        took the first ON_LINE record while ProDOS resolved the panel's path
        to either. Now refused before any block is read; a volume-list row,
        opened by its unit, still works (test_the_opened_disk_is_written_when_it_stays)."""
        writes, out, disks = self.run_disks([self.A, self.B, self.C, self.D], 'NNNNNABWx!', 'twin')
        self.assertEqual(writes, 0)
        self.assertEqual(disks, [self.A, self.B, self.C, self.D])
        self.assertEqual(out.splitlines()[1], 'Two volumes named /DISKA: pick it in the volume list.')

    def test_an_exact_copy_of_block_2_is_not_detected(self):
        """The limit, measured: disk D has disk A's block 2 byte for byte
        and other blocks elsewhere. Nothing read from block 2 can tell
        them apart, so D receives the block."""
        writes, out, disks = self.run_script('NNNNNABW@Dx!')
        self.assertEqual(writes, 1)
        self.assertEqual(disks[:3], [self.A, self.B, self.C])
        want = bytearray(self.D)
        want[2560:3072] = self.edited(self.A, 5)[2560:3072]
        self.assertEqual(disks[3], bytes(want))


CRC_SIM = r'''
#include <stdio.h>
extern unsigned char crc[4];
void __fastcall__ crc512(const unsigned char* p);
static unsigned char block[512];
int main(void)
{
    FILE* f = fopen("block.bin", "rb");
    if (!f || fread(block, 1, 512, f) != 512) return 9;
    fclose(f);
    crc512(block);
    printf("%02X%02X%02X%02X\n", crc[3], crc[2], crc[1], crc[0]);
    return 0;
}
'''


class Crc512Native(unittest.TestCase):
    """crc512 of blkedit.s, the identity W compares, assembled by each
    edition's ca65 and run under sim65 on its processor: zlib's CRC-32 of
    the block without the final inversion (the host tests use the C twin
    under PLUGIN_HOST)."""

    @classmethod
    def setUpClass(cls):
        from test_wipe import toolchains
        chains = toolchains()
        if not chains:
            raise unittest.SkipTest('no cc65 toolchain')
        cls.tmp = tempfile.TemporaryDirectory(prefix='blkedit-crc-')
        d = cls.dir = Path(cls.tmp.name)
        (d / 'harness.c').write_text(CRC_SIM)
        (d / 'crc.s').write_text((ROOT / 'src/plugins/blkedit.s').read_text())
        cls.exe = {}
        for cpu, cl65, sim65, env, cfgdir in chains:
            exe = d / f'crc-{cpu}'
            env = {**os.environ, **env}
            subprocess.run([cl65, '-t', cpu, '-O', '-o', str(exe), str(d / 'harness.c'), str(d / 'crc.s')],
                           check=True, cwd=d, env=env, capture_output=True)
            cls.exe[cpu] = (sim65, exe, env)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_matches_zlib(self):
        import random
        import zlib
        rng = random.Random(7)
        blocks = [bytes(512), b'\xff' * 512, bytes(range(256)) * 2, volume('DISKA', 1)[1024:1536]]
        blocks += [bytes(rng.randrange(256) for _ in range(512)) for _ in range(4)]
        for data in blocks:
            want = '%08X' % (zlib.crc32(data) ^ 0xFFFFFFFF)
            (self.dir / 'block.bin').write_bytes(data)
            for cpu, (sim65, exe, env) in self.exe.items():
                with self.subTest(cpu=cpu, data=data[:4].hex()):
                    out = subprocess.run([sim65, str(exe)], cwd=self.dir, env=env,
                                         capture_output=True, text=True, timeout=120)
                    self.assertEqual(out.returncode, 0, out.stderr)
                    self.assertEqual(out.stdout.strip(), want)


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
