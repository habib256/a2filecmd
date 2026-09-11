"""Exercise IMGCONV's actual sector reader with injected seek failures."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_six_plugins import PREFIX, ROOT
from po2dsk import SECTORS

HARNESS = PREFIX + r'''
static unsigned char host_track[4096];
#define TRACK host_track
#include "src/plugins/imgconv.c"
static unsigned int calls, fail_seek;
static int seek_file(FILE* f, long offset, int origin) {
    ++calls;
    if (calls == fail_seek) return -1;
    return fseek(f, offset, origin);
}
static char choose(void) { return 'P'; }
static void message(const char* s) { (void)s; }
int main(int argc, char** argv) {
    unsigned char data[512], result;
    fail_seek = atoi(argv[3]);
    if (argc > 4) {
        static struct A2fcApi api;
        static struct Panel panels[2];
        static struct Entry selected;
        static unsigned char active;
        static char destination[64], note[80];
        strcpy(panels[0].path, "/SOURCE"); strcpy(panels[1].path, "/TARGET");
        strcpy(selected.name, "INPUT.2MG"); selected.type = 6;
        { FILE* source = fopen(argv[1], "rb");
          fseek(source, 0, SEEK_END); selected.size = ftell(source); fclose(source); }
        api.panels = panels; api.active = &active; api.selected = &selected;
        api.full = argv[1]; api.other_full = destination; api.copy_buf = data; api.note = note;
        api.memcpy = memcpy; api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
        api.sprintf = sprintf; api.fopen = fopen; api.fread = fread; api.fclose = fclose;
        api.fseek = seek_file; api.message = message; api.cgetc = choose;
        /* No destination-writing callbacks: the initial seek must fail
         * before the converter attempts any output operation. */
        plugin_entry(&api);
        puts(note);
        return 0;
    }
    in = fopen(argv[1], "rb");
    buf = data; memset(buf, 0xA5, 512);
    T.fseek = seek_file; T.fread = fread;
    skind = K_DSK; sbase = 0;
    n = atoi(argv[2]);
    result = read_block();
    printf("%u\n", result);
    fwrite(buf, 1, 512, stdout);
    fclose(in);
    return 0;
}
'''


class Imgconv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='imgconv-')
        cls.root = Path(cls.tmp.name)
        source = cls.root / 'test.c'
        source.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(source), '-o', str(cls.exe)], check=True, capture_output=True)
        cls.disk = cls.root / 'input.dsk'
        cls.disk.write_bytes(b''.join(bytes([i]) * 256 for i in range(32)))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, block, failure=0):
        result = subprocess.check_output([str(self.exe), str(self.disk),
                                          str(block), str(failure)])
        status, data = result.split(b'\n', 1)
        return int(status), data

    def test_sector_order_across_tracks(self):
        for block in range(16):
            with self.subTest(block=block):
                track, pair = divmod(block, 8)
                expected = b''.join(bytes([track * 16 + sector]) * 256
                                    for sector in SECTORS[pair])
                self.assertEqual(self.read(block), (1, expected))

    def test_either_failed_seek_refuses_the_block(self):
        for block in (0, 1, 7, 8, 15):
            for seek in (1, 2):
                with self.subTest(block=block, seek=seek):
                    self.assertEqual(self.read(block, seek)[0], 0)

    def test_failed_2mg_data_seek_stops_before_destination_access(self):
        header = bytearray(64)
        header[:4] = b'2IMG'
        header[8] = 64
        header[10] = header[12] = 1
        header[20] = 8
        header[24] = 64
        header[28:32] = (4096).to_bytes(4, 'little')
        source = self.root / 'input.2mg'
        original = bytes(header) + bytes(4096)
        source.write_bytes(original)
        note = subprocess.check_output([str(self.exe), str(source), '0', '1', 'entry'],
                                       text=True).strip()
        self.assertEqual(note, 'Read failed.')
        self.assertEqual(source.read_bytes(), original)

    def test_2mg_fields_are_not_truncated_to_their_low_bytes(self):
        for offset in (13, 14, 15, 22, 23):
            with self.subTest(offset=offset):
                header = bytearray(64)
                header[:4] = b'2IMG'
                header[8] = 64
                header[10] = header[12] = 1
                header[20] = 8
                header[24] = 64
                header[28:32] = (4096).to_bytes(4, 'little')
                header[offset] = 1
                source = self.root / 'invalid.2mg'
                original = bytes(header) + bytes(4096)
                source.write_bytes(original)
                # A seek is deliberately failed if reached: malformed fields
                # must be refused as a bad header before data access begins.
                note = subprocess.check_output(
                    [str(self.exe), str(source), '0', '1', 'entry'], text=True).strip()
                self.assertEqual(note, 'Not a ProDOS-order 2IMG file.')
                self.assertEqual(source.read_bytes(), original)

    def test_2mg_data_range_is_checked_before_destination_access(self):
        for offset, size in ((0, 4096), (63, 4096), (4161, 4096),
                             (64, 4095), (0xFFFFFFFF, 4096)):
            with self.subTest(offset=offset, size=size):
                header = bytearray(64)
                header[:4] = b'2IMG'
                header[8] = 64
                header[10] = header[12] = 1
                header[20] = 8
                header[24:28] = offset.to_bytes(4, 'little')
                header[28:32] = (4096).to_bytes(4, 'little')
                source = self.root / 'range.2mg'
                source.write_bytes(header + bytes(size))
                note = subprocess.check_output(
                    [str(self.exe), str(source), '0', '1', 'entry'], text=True).strip()
                self.assertEqual(note, 'Not a ProDOS-order 2IMG file.')

    def test_2mg_padding_and_trailing_metadata_are_allowed(self):
        for offset, trailer in ((64, 0), (128, 0), (128, 73)):
            with self.subTest(offset=offset, trailer=trailer):
                header = bytearray(offset)
                header[:4] = b'2IMG'
                header[8] = 64
                header[10] = header[12] = 1
                header[20] = 8
                header[24:28] = offset.to_bytes(4, 'little')
                header[28:32] = (4096).to_bytes(4, 'little')
                source = self.root / 'padded.2mg'
                source.write_bytes(header + bytes(4096 + trailer))
                note = subprocess.check_output(
                    [str(self.exe), str(source), '0', '1', 'entry'], text=True).strip()
                self.assertEqual(note, 'Read failed.')  # reached the injected seek failure


if __name__ == '__main__':
    unittest.main()
