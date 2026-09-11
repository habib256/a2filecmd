"""Decode packed $08 pictures with the actual overlay C, against a reference."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
unsigned char host_page[8192];
#include "src/plugins/packfot.c"
static FILE* src;
static size_t rd(void* p, size_t sz, size_t n, FILE* f) { return fread(p, sz, n, src); }
static unsigned char host_aux[8192];
static int crossings;
void pf_aux_move(void) { memcpy(host_aux, host_page, 8192); ++crossings; }
void pf_show(unsigned char two) { (void)two; }
void pf_main_bank(void) {}
int main(int argc, char** argv)
{
    static unsigned char scratch[512];
    static struct A2fcApi api;
    int two = atoi(argv[2]) - 1;
    api.fread = rd; api.copy_buf = scratch;
    A = &api;
    src = fopen(argv[1], "rb");
    have = at = eof = 0;
    if (!decode((unsigned char)two)) { fprintf(stderr, "empty\n"); return 2; }
    if (two) fwrite(host_aux, 1, 8192, stdout);
    fwrite(host_page, 1, 8192, stdout);
    fclose(src);
    return crossings == two ? 0 : 3;
}
'''


def packbytes(d):
    """The reference decoder: Apple's PackBytes, as the file-type note has it."""
    out = bytearray()
    i = 0
    while i < len(d):
        b = d[i]; i += 1
        n = (b & 0x3F) + 1
        f = b >> 6
        if f == 0:   out += d[i:i + n]; i += n
        elif f == 1: out += bytes([d[i]]) * n; i += 1
        elif f == 2: out += d[i:i + 4] * n; i += 4
        else:        out += bytes([d[i]]) * (4 * n); i += 1
    return bytes(out)


class PackFot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='packfot-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decode(self, data, planes=1):
        f = self.p / 'in.bin'
        f.write_bytes(data)
        r = subprocess.run([str(self.exe), str(f), str(planes)], capture_output=True)
        return r.returncode, r.stdout

    def pack_literals(self, payload):
        """`payload` as flag-0 packets of 64 bytes: the shortest thing to write."""
        out = bytearray()
        for i in range(0, len(payload), 64):
            chunk = payload[i:i + 64]
            out.append(len(chunk) - 1)
            out += chunk
        return bytes(out)

    def test_the_four_packet_kinds(self):
        stream = bytes([0x02, 1, 2, 3,          # 3 literals
                        0x41, 0xAA,             # 2 x $AA
                        0x81, 9, 8, 7, 6,       # 2 x the four bytes
                        0xC1, 0x55])            # 8 x $55
        rc, out = self.decode(stream)
        self.assertEqual(rc, 0)
        want = bytes([1, 2, 3]) + b'\xAA' * 2 + bytes([9, 8, 7, 6]) * 2 + b'\x55' * 8
        self.assertEqual(out[:len(want)], want)
        self.assertEqual(out[len(want):], b'\x00' * (8192 - len(want)))
        self.assertEqual(len(out), 8192)

    def test_matches_the_reference_decoder(self):
        payload = bytes((i * 7 + (i >> 5)) & 0xFF for i in range(8192))
        rc, out = self.decode(self.pack_literals(payload))
        self.assertEqual(rc, 0)
        self.assertEqual(out, payload)
        self.assertEqual(out, packbytes(self.pack_literals(payload)))

    def test_a_packer_that_drops_the_tail_is_not_refused(self):
        """One reference picture stops a byte short of the page: zero-fill it."""
        payload = b'\xFF' * 8191
        rc, out = self.decode(self.pack_literals(payload))
        self.assertEqual(rc, 0)
        self.assertEqual(out, payload + b'\x00')

    def test_a_packet_cut_by_the_end_of_the_file(self):
        rc, out = self.decode(bytes([0x3F, 1, 2, 3]))     # 64 literals, only 3 there
        self.assertEqual(rc, 0)
        self.assertEqual(out[:3], b'\x01\x02\x03')
        self.assertEqual(len(out), 8192)

    def test_an_overlong_packet_stops_at_the_end_of_the_page(self):
        """A run past $3FFF must not write into whatever follows the page."""
        rc, out = self.decode(bytes([0x7F, 0xEE]) * 200)  # 64 x $EE, over and over
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 8192)
        self.assertEqual(out, b'\xEE' * 8192)

    def test_an_empty_file_is_refused(self):
        self.assertEqual(self.decode(b'')[0], 2)

    def test_a_packet_straddling_the_two_planes(self):
        """The two planes are ONE stream: a packet crossing 8192 must not
        lose its tail to the bank move."""
        payload = bytes(range(256)) * 64                 # 16384 bytes, all distinct runs
        stream = bytearray()
        for i in range(0, 16384, 64):                    # 64-byte literal packets
            stream.append(63)
            stream += payload[i:i + 64]
        # shift the packet boundary so one of them straddles 8192
        stream = bytearray([0x00, payload[0]]) + stream[:1] + stream[1:]
        rc, out = self.decode(bytes(stream), planes=2)
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 16384)
        self.assertEqual(out, bytes([payload[0]]) + packbytes(bytes(stream))[1:16384])

    def test_two_planes_are_decoded_in_a_row(self):
        first, second = b'\x11' * 8192, b'\x22' * 8192
        stream = self.pack_literals(first) + self.pack_literals(second)
        rc, out = self.decode(stream, planes=2)
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 16384)
        self.assertEqual(out, first + second)


if __name__ == '__main__':
    unittest.main()
