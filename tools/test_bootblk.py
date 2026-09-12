"""Execute BOOTBLK's entrypoint with faults before/after physical I/O."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static unsigned char original[1024], replacement[1024];
#define ORIGINAL original
#define REPLACEMENT replacement
#include "src/plugins/bootblk.c"
static unsigned char disks[2][1536];
static unsigned int calls, writes, fail1, fail2;
static int mode, consent, same;
static unsigned char mock(unsigned char cmd, void* p) {
    struct Blk* io = p;
    unsigned char *disk;
    int fault;
    if (cmd == 0xC5) {
        struct Onl* o = p;
        memset(o->buf, 0, 256);
        o->buf[0] = 0x64; memcpy(o->buf + 1, "BOOT", 4);
        o->buf[16] = 0xD6; memcpy(o->buf + 17, "TARGET", 6);
        return 0;
    }
    ++calls;
    if ((cmd != 0x80 && cmd != 0x81) || io->block > 1) abort();
    if (io->unit != 0x60 && io->unit != 0xD0) abort();
    disk = disks[io->unit == 0xD0] + io->block * 512;
    fault = calls == fail1 || calls == fail2;
    if (cmd == 0x81) {
        if (io->unit != 0xD0) abort(); /* never write the source */
        ++writes;
    }
    if (fault && mode == 0) return 0x27;
    if (cmd == 0x80) memcpy(io->buf, disk, 512);
    else memcpy(disk, io->buf, 512);
    if (fault) {
        if (mode == 1) return 0x27; /* completed I/O, then error */
        if (cmd == 0x80) io->buf[511] ^= 0x80;
        else disk[511] ^= 0x80; /* silent corruption caught by readback */
    }
    return 0;
}
static unsigned char confirm(const char* s) { (void)s; return consent; }
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    static char note[80];
    FILE* f;
    unsigned int i;
    fail1 = atoi(argv[1]); fail2 = atoi(argv[2]); mode = atoi(argv[3]);
    consent = atoi(argv[4]); same = atoi(argv[5]);
    for (i = 0; i < 1536; ++i) {
        disks[0][i] = (i * 17 + i / 512) & 255;
        disks[1][i] = (i * 7 + 93 + i / 512) & 255;
    }
    strcpy(selected.name, same ? "/BOOT" : "/TARGET");
    selected.mdate = same ? 6 : 13;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note; api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.strcpy = strcpy; api.mli = mock; api.confirm = confirm;
    plugin_entry(&api);
    f = fopen(argv[6], "wb"); fwrite(disks, 1, sizeof disks, f); fclose(f);
    printf("%u %u\n%s\n", calls, writes, note);
    return 0;
}
'''


class BootBlocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='bootblk-faults-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)
        cls.source = bytes((i * 17 + i // 512) & 255 for i in range(1536))
        cls.target = bytes((i * 7 + 93 + i // 512) & 255 for i in range(1536))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, fail=0, second=0, mode=0, consent=1, same=0):
        path = self.root / 'result.bin'
        result = subprocess.check_output([str(self.exe), str(fail), str(second),
                  str(mode), str(consent), str(same), str(path)], text=True)
        counts, note = result.split('\n', 1)
        calls, writes = map(int, counts.split())
        data = path.read_bytes()
        self.assertEqual(data[:1536], self.source, 'source must remain untouched')
        self.assertEqual(data[2560:], self.target[1024:], 'no filesystem block writes')
        return calls, writes, note, data[1536:]

    def test_success_verifies_both_blocks(self):
        calls, writes, note, target = self.run_case()
        self.assertEqual((calls, writes), (8, 2))
        self.assertEqual(target, self.source[:1024] + self.target[1024:])
        self.assertIn('rewritten from', note)

    def test_all_preflight_read_failures_write_nothing(self):
        for mode in (0, 1):
            for fail in range(1, 5):
                with self.subTest(mode=mode, fail=fail):
                    calls, writes, note, target = self.run_case(fail, mode=mode)
                    self.assertEqual(writes, 0)
                    self.assertEqual(target, self.target)
                    self.assertIn('nothing written', note)

    def test_install_errors_before_and_after_io_restore_both_originals(self):
        for mode in (0, 1, 2):
            for fail in range(5, 9):
                with self.subTest(mode=mode, fail=fail):
                    calls, writes, note, target = self.run_case(fail, mode=mode)
                    self.assertEqual(target, self.target)
                    self.assertIn('both original blocks restored and verified', note)
                    self.assertGreaterEqual(writes, 3)

    def test_failed_restore_reports_incomplete_and_still_attempts_other_block(self):
        # Failure on second installation write (call 7), then each rollback I/O.
        for mode in (0, 1, 2):
            for offset in range(4):
                start = 9 if mode == 2 else 8
                second = start + offset
                with self.subTest(mode=mode, second=second):
                    calls, writes, note, target = self.run_case(8 if mode == 2 else 7, second, mode)
                    self.assertIn('BOOT RESTORE FAILED', note)
                    self.assertEqual(writes, 4, 'both restoration writes must be attempted')
                    if offset < 2:
                        self.assertEqual(target[512:], self.target[512:])
                    else:
                        self.assertEqual(target[:512], self.target[:512])

    def test_declining_does_not_read_or_write_blocks(self):
        calls, writes, note, target = self.run_case(consent=0)
        self.assertEqual((calls, writes), (0, 0))
        self.assertEqual(target, self.target)

    def test_source_volume_is_refused(self):
        calls, writes, note, target = self.run_case(same=1)
        self.assertEqual((calls, writes), (0, 0))
        self.assertIn('volume booted from', note)
        self.assertEqual(target, self.target)


if __name__ == '__main__':
    unittest.main()
