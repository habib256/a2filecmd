"""Decode 816/Paint packed pictures with the actual overlay C, against a
reference built the other way round (a page in, a packed file out).

The format is not documented anywhere; it was read off chosen-plaintext
pairs -- raw pages written to a disk, packed by 816/Paint itself, and the
two compared -- so the record shapes checked here are the ones that really
occur in its output, quoted from those files.
"""
import base64
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
/* The page sits inside a fenced arena: a decoder that walks off the plane --
 * past the last column, or past row 191 -- disturbs a fence and the harness
 * says so instead of quietly writing over its own memory. */
static unsigned char arena[256 + 8192 + 256];
static unsigned char* host_page = arena + 256;
static FILE* src;
static size_t rd(void* p, size_t sz, size_t n, FILE* f) { return fread(p, sz, n, src); }

/* p8_put and p8_top are paint816.s on an Apple II: the hi-res geometry is
 * 6502 there because cc65 spends a thirteenth of the whole window on it.
 * What follows is the same rule written plainly, so that the tests below
 * exercise the RECORD GRAMMAR against it; the shipped 6502 version of the
 * geometry is checked in the emulator instead (tools/pom2_paint816.py). */
unsigned char p8_col;
static unsigned char p8_row;
void p8_top(void) { p8_col = 39; p8_row = 0; }
void __fastcall__ p8_put(unsigned char v)
{
    unsigned int a;
    if (p8_col & 0x80) return;
    a = ((p8_row & 7) << 10) | ((p8_row & 0x38) << 4) | ((p8_row >> 6) * 40);
    host_page[a + p8_col] = v;
    if (++p8_row == 192) { p8_row = 0; --p8_col; }
}
#include "src/plugins/paint816.c"
static unsigned char host_aux[8192];
static int crossings;
void p8_aux_move(void) { memcpy(host_aux, host_page, 8192); ++crossings; }
void p8_show(unsigned char two) { (void)two; }
void p8_main_bank(void) {}
int main(int argc, char** argv)
{
    static unsigned char scratch[512];
    static struct A2fcApi api;
    int two = atoi(argv[2]) - 1, i;
    api.fread = rd; api.copy_buf = scratch;
    A = &api;
    src = fopen(argv[1], "rb");
    memset(arena, 0x5A, sizeof arena);
    memset(host_page, 0xEE, 8192);            /* nothing may be left unwritten */
    have = at = 0;
    if (!picture((unsigned char)two)) { fprintf(stderr, "refused\n"); return 2; }
    for (i = 0; i < 256; ++i)
        if (arena[i] != 0x5A || arena[256 + 8192 + i] != 0x5A) {
            fprintf(stderr, "wrote outside the page\n");
            return 4;
        }
    if (two) fwrite(host_aux, 1, 8192, stdout);
    fwrite(host_page, 1, 8192, stdout);
    fclose(src);
    return crossings == two ? 0 : 3;
}
'''

ROWS, COLS = 192, 40


def addr(r):
    """The hi-res address of display row r within an 8 KB page."""
    return ((r & 7) << 10) | ((r & 0x38) << 4) | ((r >> 6) * 40)


def page_of(stream):
    """The 8 KB plane whose 816/Paint stream -- rightmost column first, rows
    0..191 down it -- is `stream`. The screen holes stay 0."""
    p = bytearray(8192)
    for c in range(COLS):
        for r in range(ROWS):
            p[addr(r) + COLS - 1 - c] = stream[c * ROWS + r]
    return bytes(p)


def page_left_to_right(stream):
    """The same, for a stream written the OTHER way round -- column 0 first.
    The two real files below were made from pages described that way; using
    page_of for them would silently mirror the picture and prove nothing."""
    p = bytearray(8192)
    for c in range(COLS):
        for r in range(ROWS):
            p[addr(r) + c] = stream[c * ROWS + r]
    return bytes(p)


def stream_of(page):
    """The other way: a plane's 7,680 picture bytes in 816/Paint's order."""
    return bytes(page[addr(r) + COLS - 1 - c]
                 for c in range(COLS) for r in range(ROWS))


def pack(stream, plen=1):
    """A reference packer: runs of a `plen`-byte pattern where there is one,
    literals elsewhere. Not 816/Paint's own choices -- the point is that any
    legal encoding of a page decodes back to it."""
    out = bytearray(b'\xff')
    i, lit = 0, bytearray()

    def flush():
        while lit:
            n = min(len(lit), 127)
            out.append(n)
            out.extend(lit[:n])
            del lit[:n]

    while i < len(stream):
        n = 0
        while i + n < len(stream) and stream[i + n] == stream[i + n % plen]:
            n += 1
        if n >= plen * 2 and n >= 3:
            flush()
            tag = 0x80 | {1: 0, 2: 1, 4: 2, 8: 3}[plen]
            if n <= 31 * 1:
                out.append(tag | (n << 2))
            else:
                n = min(n, 255)
                out.append(tag)
                out.append(n)
            out.extend(stream[i:i + plen])
            i += n
        else:
            lit.append(stream[i])
            i += 1
    flush()
    return bytes(out)


def literals(stream):
    """Every byte a literal, in the longest blocks the tag allows."""
    out = bytearray(b'\xff')
    for i in range(0, len(stream), 127):
        chunk = stream[i:i + 127]
        out.append(len(chunk))
        out.extend(chunk)
    return bytes(out)


TRAILER = b'\x07816PATT' + bytes(64)


# -- two files 816/Paint itself wrote, straight off the disk ----------------
# The pages they came from are rebuilt below from their own descriptions, not
# from this decoder, so these two assert the FORMAT and not just that the code
# has not changed. LADDER exercises every pattern length and both count forms;
# RUNS is a double hi-res file, so it also pins the eight-byte prefix, the
# second marker and the plane order.
LADDER_PACKED = base64.b64decode(
    '/4BRf4BXANx/AX+4AIBWf4BWAJR/AX+AJACAVX+ARgABAIA8AIBUf4AvAAEAkH+AUgCAU3/Y'
    'AAEAgCF/gFEAgE1/AX+AQH+AUACAL38Bf8gAgE9/gE8AvH8Bf4A2AIBOf4A7AAEAwH+ATACA'
    'TX/YAAEAgDl/gEsAgDt/AX/oAIBKf4BKAMR/AX+ASACASX+ALgABAIAxf4BHAIBHfwF/+ACA'
    'Rn+ARgDUfwF/wH+ARACARX+AJgABAJgAgEN/gEMAgDN/AX8Bf4BBAIBCf4A7AAEAgEB/gEAA'
    'gD9/AX+Qf4A+AIA/f4A+AAEAsACAPX+APQCAOX8Bf+R/gDsAgDx/gC8AAQCAKgCAOn+AOgCA'
    'IX8Bf6AAgDh/gDgAgDl/uAABAIAkf4A2AIA3f4AuAAEAwH+ANACANX+ANQDEfwF/kH+AMgCA'
    'M3+AMwCAI38Bf4AwAIAxf4AxAIAtfwF/kH+ALgCAL3+ALwCAL38Bf8B/gCwAgC1/gC0AgCl/'
    'AX+AJH+AKgCAK3+AKwDsfwF/4ACAKH+AKACAKX+AKQCUfwF/5H+AJQCAJn+AJgCAJ3+4AAEA'
    'kH+AIgCAI3+AIwCAJH+AJACsfwF/AX/8AIAgf4AgAIAhf4AhAPR/AX/Af/AA9H/0APh/+AD0'
    'fwF/4ADkf+QA6H/oAOx/7ACsfwF/wH/QANR/1ADYf9gA3H/cANx/AX+Qf7gAvH+8AMB/wADE'
    'f8QAyH/IAMx/zAAEf39/fwF/ngB/fwABf78AAAB/f39/AAF/lACYf5gAnH+cAKB/oACkf6QA'
    'qH+oAKx/rACwf7AAtH+0AKR/AX8HODE2UEFUVN2AVYDdgN2A3YBVgN2A3YB3gC6AHIA6gHeA'
    'o4DBgOKA8ICZgA+AD4APgJmA8IDwgACAKoAAgKKAAIAqgACAooA=')
RUNS_PACKED = base64.b64decode(
    'AABVVQAqKgD/gL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEA'
    'gL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwAB'
    'AIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAWAOAZwABAIC/AwED'
    'gL8DAQOAQACAfwMBA4C/AAEAgJQqgCsAAQCAvyoBKoCEAIA7KgEq4FWApwABAIC/VQFVgGwA'
    'gFNVAVWAvwABAP+AvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8A'
    'AQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/'
    'AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgL8AAQCAvwABAIC/AAEAgFgDgGcA'
    'AQCAvwMBA4C/AwEDgEAAgH8DAQOAvwABAICUKoArAAEAgL8qASqAhACAOyoBKuBVgKcAAQCA'
    'v1UBVYBsAIBTVQFVBzgxNlBBVFQfHxERHx8fHx8fEREfHx8f4NAADdDgDgDg0AAN0OAOADw8'
    '8A/wD/APPDwP8A/wD/AAAIiAAACAiAAAiIAAAICI')


def ladder_stream():
    """Runs of 1, 1, 2, 2, 3, 3 ... bytes of $7F and $00, down the columns."""
    s = bytearray()
    k = 1
    while len(s) < COLS * ROWS:
        s += bytes([0x7F]) * k + bytes(k)
        k += 1
    return bytes(s[:COLS * ROWS])


def runs_stream():
    """Three long runs of values that are not the background, on a zero page."""
    s = bytearray(COLS * ROWS)
    for start, val, n in ((300, 0x55, 300), (900, 0x2A, 400), (1600, 0x03, 600)):
        s[start:start + n] = bytes([val]) * n
    return bytes(s)


class Paint816(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='paint816-')
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

    def pic(self, got, want_page):
        """Compare only what is on the screen: the format carries no holes."""
        for i in range(0, len(want_page), 128):
            self.assertEqual(got[i:i + 120], want_page[i:i + 120],
                             'row group at %d' % i)

    # -- the records, exactly as 816/Paint writes them ----------------------
    def test_solid_column_as_816paint_writes_it(self):
        """H01.SOLID packed: `80 BF 2A 01 2A` per column -- an extended
        one-byte run of 191 and the last byte as a literal, forty times."""
        d = b'\xff' + b'\x80\xbf\x2a\x01\x2a' * COLS + TRAILER
        rc, out = self.decode(d)
        self.assertEqual(rc, 0)
        self.pic(out, page_of(bytes([0x2A]) * (COLS * ROWS)))

    def test_two_byte_pattern_run(self):
        """H04.ALT packed: `81 BF 00 7F 01 7F` -- tag bits 1-0 = 1, so a
        two-byte pattern, 191 BYTES of it, then the odd last byte."""
        d = b'\xff' + b'\x81\xbf\x00\x7f\x01\x7f' * COLS + TRAILER
        rc, out = self.decode(d)
        self.assertEqual(rc, 0)
        self.pic(out, page_of(bytes(0x00 if r % 2 == 0 else 0x7F
                                    for c in range(COLS) for r in range(ROWS))))

    def test_four_and_eight_byte_pattern_runs(self):
        """H03.LADDER packed: `9E 00 7F 7F 00` is seven bytes of a four-byte
        pattern, `BF 00 00 00 7F 7F 7F 7F 00` fifteen of an eight-byte one --
        a count of BYTES, so both stop mid-pattern."""
        head = b'\x9e\x00\x7f\x7f\x00' b'\x00\x01\x7f' b'\xbf\x00\x00\x00\x7f\x7f\x7f\x7f\x00'
        want = bytearray(b'\x00\x7f\x7f\x00\x00\x7f\x7f' b'\x7f'
                         + (b'\x00\x00\x00\x7f\x7f\x7f\x7f\x00' * 2)[:15])
        rc, out = self.decode(b'\xff' + head + literals(bytes(COLS * ROWS - len(want)))[1:]
                              + TRAILER)
        self.assertEqual(rc, 0)
        self.assertEqual(stream_of(out)[:len(want)], bytes(want))

    def test_inline_counts_are_bits_six_to_two(self):
        """A pattern tag carries its count in bits 6-2, not the low six: DC
        is 23 bytes and E0 is 24, both of a one-byte pattern."""
        rc, out = self.decode(b'\xff\xdc\x11\xe0\x22'
                              + literals(bytes(COLS * ROWS - 47))[1:] + TRAILER)
        self.assertEqual(rc, 0)
        self.assertEqual(stream_of(out)[:47], bytes([0x11]) * 23 + bytes([0x22]) * 24)

    def test_literal_tag_is_its_own_count(self):
        rc, out = self.decode(b'\xff\x03\xaa\xbb\xcc'
                              + literals(bytes(COLS * ROWS - 3))[1:] + TRAILER)
        self.assertEqual(rc, 0)
        self.assertEqual(stream_of(out)[:3], b'\xaa\xbb\xcc')

    def test_literal_tag_zero_takes_an_extended_count(self):
        """H05.COUNT packed opens `00 C0` and 192 bytes: a whole column."""
        body = bytes(range(0xC0))
        rc, out = self.decode(b'\xff\x00\xc0' + body
                              + literals(bytes(COLS * ROWS - 0xC0))[1:] + TRAILER)
        self.assertEqual(rc, 0)
        self.assertEqual(stream_of(out)[:0xC0], body)

    # -- the geometry ------------------------------------------------------
    def test_the_rightmost_column_comes_first(self):
        """One byte set, everything else background: it must land in column
        39, not column 0. This is the whole of the column order."""
        s = bytearray(COLS * ROWS)
        s[7] = 0x7F
        rc, out = self.decode(literals(bytes(s)) + TRAILER)
        self.assertEqual(rc, 0)
        self.assertEqual(out[addr(7) + COLS - 1], 0x7F)
        self.assertEqual(sum(1 for i in range(8192)
                             if (i % 128) < 120 and out[i]), 1)

    def test_a_column_runs_top_to_bottom(self):
        s = bytes((r & 0x7F) for c in range(COLS) for r in range(ROWS))
        rc, out = self.decode(literals(s) + TRAILER)
        self.assertEqual(rc, 0)
        for r in (0, 1, 7, 8, 63, 64, 65, 127, 128, 191):
            self.assertEqual(out[addr(r) + COLS - 1], r & 0x7F, 'row %d' % r)

    def test_every_visible_byte_is_written(self):
        """The harness fills the page with $EE first: a plane must leave
        none of it behind on the screen."""
        s = bytes(COLS * ROWS)
        rc, out = self.decode(literals(s) + TRAILER)
        self.assertEqual(rc, 0)
        self.assertFalse([i for i in range(8192) if (i % 128) < 120 and out[i] != 0])

    def test_screen_holes_are_left_alone(self):
        rc, out = self.decode(literals(bytes(COLS * ROWS)) + TRAILER)
        self.assertEqual(rc, 0)
        self.assertTrue(all(out[i] == 0xEE for i in range(8192) if (i % 128) >= 120))

    # -- whole pictures ----------------------------------------------------
    def test_round_trip_every_pattern_length(self):
        s = bytes(((r // 5) * 7 + c) & 0x7F for c in range(COLS) for r in range(ROWS))
        for plen in (1, 2, 4, 8):
            rc, out = self.decode(pack(s, plen) + TRAILER, 1)
            self.assertEqual(rc, 0, 'plen %d' % plen)
            self.pic(out, page_of(s))

    def test_double_hi_res_is_two_planes_auxiliary_first(self):
        a = bytes((c * 3 + r) & 0x7F for c in range(COLS) for r in range(ROWS))
        m = bytes((c * 5 + r * 2) & 0x7F for c in range(COLS) for r in range(ROWS))
        d = bytes(8) + pack(a) + pack(m) + TRAILER
        rc, out = self.decode(d, 2)
        self.assertEqual(rc, 0)
        self.assertEqual(len(out), 16384)
        self.pic(out[:8192], page_of(a))
        self.pic(out[8192:], page_of(m))

    def test_the_eight_byte_prefix_is_skipped_not_decoded(self):
        """It is a copy of the auxiliary plane's first eight bytes and the
        stream carries them again; taking it for records would desynchronise
        the whole file."""
        a = bytes((c ^ r) & 0x7F for c in range(COLS) for r in range(ROWS))
        m = bytes(COLS * ROWS)
        page = page_of(a)
        d = page[:8] + pack(a) + pack(m) + TRAILER
        rc, out = self.decode(d, 2)
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page)

    # -- refusals and damage ----------------------------------------------
    def test_a_missing_marker_is_refused(self):
        rc, _ = self.decode(b'\x00' + literals(bytes(COLS * ROWS))[1:] + TRAILER)
        self.assertEqual(rc, 2)

    def test_an_empty_file_is_refused(self):
        self.assertEqual(self.decode(b'')[0], 2)

    def test_a_truncated_stream_is_padded_not_refused(self):
        s = bytes([0x55]) * (COLS * ROWS)
        full = pack(s)
        rc, out = self.decode(full[:len(full) // 2])
        self.assertEqual(rc, 0)
        st = stream_of(out)
        self.assertEqual(st[:100], bytes([0x55]) * 100)
        self.assertEqual(st[-100:], bytes(100))

    def test_a_run_cannot_spill_past_the_last_column(self):
        """An extended count of 255 on the last bytes of the page: the write
        has to stop at column 0 row 191 and not walk off the plane."""
        d = b'\xff' + literals(bytes(COLS * ROWS - 4))[1:] + b'\x80\xff\x99' + TRAILER
        rc, out = self.decode(d)
        self.assertEqual(rc, 0)
        self.assertEqual(stream_of(out)[-4:], bytes([0x99]) * 4)

    # -- the real thing ----------------------------------------------------
    def test_real_hi_res_file_from_816paint(self):
        """H03.LADDER packed by 816/Paint, 686 bytes for an 8 KB page."""
        rc, out = self.decode(LADDER_PACKED, 1)
        self.assertEqual(rc, 0)
        self.pic(out, page_left_to_right(ladder_stream()))

    def test_real_double_hi_res_file_from_816paint(self):
        """D06.RUNS packed by 816/Paint: two planes, the main one the same
        picture moved one column to the left, which is what tells the plane
        order apart."""
        s = runs_stream()
        shifted = bytes(s[((c + 1) % COLS) * ROWS + r]
                        for c in range(COLS) for r in range(ROWS))
        rc, out = self.decode(RUNS_PACKED, 2)
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_left_to_right(s))
        self.pic(out[8192:], page_left_to_right(shifted))


if __name__ == '__main__':
    unittest.main(verbosity=2)
