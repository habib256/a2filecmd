"""Run WIPE F against valid and damaged volume metadata; inspect every byte."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static unsigned char bitmap_buffer[512], zero_buffer[512], keyboard;
#define BM bitmap_buffer
#define ZERO zero_buffer
#define KBD keyboard
#define KBDSTRB keyboard
#include "src/plugins/wipe.c"
static FILE* disk;
static unsigned int writes;
static unsigned char mock_mli(unsigned char cmd, void* p) {
    struct Bp* b = p;
    if (cmd == 0xC5) return 0x27; /* selected volume already supplies its unit */
    if (cmd != 0x80 && cmd != 0x81) return 1;
    if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
    if (cmd == 0x80) return fread(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
    ++writes;
    return fwrite(b->buf, 1, 512, disk) == 512 ? 0 : 0x27;
}
static char choose(void) { return 'F'; }
static unsigned char confirm(const char* s) { (void)s; return 1; }
static void message(const char* s) { (void)s; }
static void progress(const char* s, unsigned long d, unsigned long t)
{ (void)s; (void)d; (void)t; }
int main(int argc, char** argv) {
    static struct A2fcApi api;
    static struct Panel panels[2];
    static struct Entry selected;
    static unsigned char active, copy[512];
    static char note[80];
    disk = fopen(argv[1], "r+b");
    strcpy(selected.name, "/WIPE"); selected.access = 1; selected.mdate = 6;
    api.panels = panels; api.active = &active; api.selected = &selected;
    api.copy_buf = copy; api.note = note; api.cfg_path = "/BOOT/A2FILE/A2FILE.CFG";
    api.memcpy = memcpy; api.memset = memset; api.strcpy = strcpy;
    api.strcmp = strcmp; api.sprintf = sprintf; api.mli = mock_mli;
    api.cgetc = choose; api.confirm = confirm; api.message = message;
    api.progress_bar = progress;
    plugin_entry(&api);
    printf("%u\n%s\n", writes, note);
    fclose(disk); return 0;
}
'''


class Wipe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='wipe-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def volume(self, total=280, bitmap=6):
        data = bytearray(b'\xA5' * (512 * total))
        data[1024:1536] = bytes(512)
        data[1028] = 0xF4
        data[1024 + 0x27:1024 + 0x29] = bitmap.to_bytes(2, 'little')
        data[1024 + 0x29:1024 + 0x2B] = total.to_bytes(2, 'little')
        return data

    def run_wipe(self, data):
        disk = self.root / 'disk.po'
        disk.write_bytes(data)
        output = subprocess.check_output([str(self.exe), str(disk)], text=True, timeout=15)
        count, note = output.split('\n', 1)
        return int(count), note.strip(), disk.read_bytes()

    def test_only_the_free_block_is_zeroed(self):
        data = self.volume()
        data[6 * 512:7 * 512] = bytes(512)
        data[6 * 512 + 20 // 8] = 0x80 >> (20 & 7)
        writes, note, after = self.run_wipe(data)
        data[20 * 512:21 * 512] = bytes(512)
        self.assertEqual(writes, 1)
        self.assertEqual(after, data)
        self.assertIn('1 blocks zeroed', note)

    def test_invalid_bitmap_location_never_writes(self):
        for total, bitmap in ((280, 0), (280, 1), (280, 2), (280, 280),
                              (280, 65535), (5000, 4999)):
            with self.subTest(total=total, bitmap=bitmap):
                data = self.volume(total, bitmap)
                writes, note, after = self.run_wipe(data)
                self.assertEqual(writes, 0)
                self.assertIn('Invalid volume bitmap', note)
                self.assertEqual(after, data)


if __name__ == '__main__':
    unittest.main()
