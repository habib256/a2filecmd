"""Decode Extasie $F2 pictures with the actual overlay C, against a reference.

The format is not documented anywhere; it was read off the ten pictures on
the original Extasie disks, every one of which decodes to exactly 15,360
bytes -- forty columns of 192 for the auxiliary plane and forty for the
main -- and to a coherent image. BASTILLE below is one of them, byte for
byte, so this file pins the FORMAT and not merely today's decoder.
"""
import base64
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
/* The page sits inside a fenced arena: a decoder that walks off the plane --
 * past the last column, or past row 191 -- disturbs a fence and the harness
 * says so instead of quietly writing over its own memory. */
static unsigned char arena[256 + 8192 + 256];
static unsigned char* host_page = arena + 256;
static FILE* src;
static size_t rd(void* p, size_t sz, size_t n, FILE* f) { return fread(p, sz, n, src); }
static int hseek(FILE* f, long off, int whence) { return fseek(src, off, whence); }

/* ex_put and ex_top are extasie.s on an Apple II: the hi-res geometry is 6502
 * there because cc65 spends a tenth of the whole window on it. What follows
 * is the same rule written plainly, so that the tests below exercise the
 * STREAM against it; the shipped 6502 geometry is checked in the emulator
 * instead (bench/extasie.py). */
unsigned char ex_col;
static unsigned char ex_row, ex_plane;
static unsigned char host_aux[8192];
static int crossings;
void ex_aux_move(void) { memcpy(host_aux, host_page, 8192); ++crossings; }
void ex_top(void) { ex_col = 0; ex_row = 0; ex_plane = 0; }
void __fastcall__ ex_put(unsigned char v)
{
    unsigned int a;
    if (ex_col >= 40) return;
    a = ((ex_row & 7) << 10) | ((ex_row & 0x38) << 4) | ((ex_row >> 6) * 40);
    host_page[a + ex_col] = v;
    if (++ex_row < 192) return;
    ex_row = 0;
    if (++ex_col < 40 || ex_plane) return;
    ex_plane = 1;                        /* the auxiliary plane is full */
    ex_aux_move();
    ex_col = 0;
}
#include "src/plugins/extasie.c"
void ex_show(void) {}
void ex_main_bank(void) {}
int main(int argc, char** argv)
{
    static unsigned char scratch[512];
    static struct A2fcApi api;
    int i;
    api.fread = rd; api.fseek = hseek; api.copy_buf = scratch;
    A = &api;
    src = fopen(argv[1], "rb");
    memset(arena, 0x5A, sizeof arena);
    memset(host_page, 0xEE, 8192);            /* nothing may be left unwritten */
    if (!picture()) { fprintf(stderr, "truncated\n"); return 2; }
    for (i = 0; i < 256; ++i)
        if (arena[i] != 0x5A || arena[256 + 8192 + i] != 0x5A) {
            fprintf(stderr, "wrote outside the page\n");
            return 4;
        }
    fwrite(host_aux, 1, 8192, stdout);
    fwrite(host_page, 1, 8192, stdout);
    fclose(src);
    return crossings == 1 ? 0 : 3;
}
"""

ROWS, COLS = 192, 40


def addr(r):
    """The hi-res address of display row r within an 8 KB page."""
    return ((r & 7) << 10) | ((r & 0x38) << 4) | ((r >> 6) * 40)


def page_of(stream):
    """The 8 KB plane whose Extasie stream -- leftmost column first, rows
    0..191 down it -- is `stream`. The screen holes stay 0."""
    p = bytearray(8192)
    for c in range(COLS):
        for r in range(ROWS):
            p[addr(r) + c] = stream[c * ROWS + r]
    return bytes(p)


def unrle(d):
    """The reference decoder, written straight from the rule: the low seven
    bits of a byte are a count (0 meaning 128), bit 7 says whether one byte
    repeats or that many follow as they are. The two-byte header is the
    file's own length."""
    out = bytearray()
    i = 2
    while i < len(d):
        c = d[i]; i += 1
        n = (c & 0x7F) or 128
        if c & 0x80:
            out += bytes([d[i]]) * n; i += 1
        else:
            out += d[i:i + n]; i += n
    return bytes(out)


def rle(stream, run=128):
    """A packer for made-up pictures: runs where there are runs, literals
    elsewhere. Not Extasie's own choices -- the point is that any legal
    encoding of a page decodes back to it."""
    out = bytearray()
    i, lit = 0, bytearray()

    def flush():
        while lit:
            n = min(len(lit), 127)
            out.append(n)
            out.extend(lit[:n])
            del lit[:n]

    while i < len(stream):
        n = 1
        while i + n < len(stream) and stream[i + n] == stream[i] and n < run:
            n += 1
        if n >= 3:
            flush()
            out.append(0x80 | (n & 0x7F))
            out.append(stream[i])
            i += n
        else:
            lit.append(stream[i])
            i += 1
    flush()
    return bytes(out)


def header(payload):
    n = len(payload) + 2
    return bytes([n & 0xFF, n >> 8]) + payload


BASTILLE = base64.b64decode(   # 3,397 bytes, off an original Extasie disk
    'RQ2xgI8AjICVAAGAwgCFgJcA/4DfgKoAkYCXAIiAlwCJgKgAAYD/AMAAAYD/AMAAAYDmAAGA8ACG'
    'gAEAhIDEAIKA/wCcAIWAxACEgIQAhYCFAISAhACFgIQAhYCEAImA/wC/AIOAhgACQGCCMAJgQIMA'
    'AkBggjACYECDAAJAYIIwAmBAgwACQGCCMAJgQIMAAkBggjACYECDAAJAYIIwAmBAgwACQGCCMAJg'
    'QIMAAkBggjACYECDAAJAYIIwAmBAgwACQGCCMAJgQIMAAkBggjACYECDAAJAYIIwAmBAgwACQGCC'
    'MAJgQIMAAkBggjACYECDAAJAYIIwAmBAgwACQGCCMAJgQIMAAkBggjACYECDAAJAYIIwAmBAgwAC'
    'QGCCMAJgQIMAAkBggjACYECGAIKAgwABf/9MtkwCfB+DAIKAgwACYDz/M5czAgNjgjMBc4IzA3Mz'
    'I4JjhEOFA4kzAj94gwCCgIQAAgN8/0yYTARJQgIEgn8BB4JAgiAIEQ4IFGQCEQCITAJ/QIQAgoCD'
    'AAIfc/8zmjMFA3h/X1CCCAgEBwYKMkEBCIIEAQCIMwNzOweDAIKAgwACeE//TJlMAQCCf4IgghCC'
    'CAYFBgoSYQGDEAEAiUwCTX6DAIKAhAACQD+FMwsTA0FhYHh8Hg4UD4JPD0cnJgcRFDd/bV09VTVn'
    'RYIAARPxMwIBcIJ/gkiCDA1yAgFDREhQIkJ+AHwAiDMCP3CEAIKAgwACBzyHTAVAQkBBQJRMBUhB'
    'Qw8/gn8IeGxYQgggBAzdTAEMggQBcIIABRBwUAB+gj8BVIJSAlExgnACdHaCdAV1czQ4f4IAiEwD'
    'fA4BgwCCgIMAAX6oMwIgT4R/BX5iKmABhAOIE8wzBhMAfwB/AIR/DThHFxsdXW5vD19PVzmCfgh9'
    'O1dPD3B/AIozAX+DAIKAhAACcE+STIIMAUSCcAQYDAR+gn8EfTdvHYN/BH5/D2CCfwN+en+Cfox/'
    'ChsZARdGLQh4BFKCZARhZGElhGGDMQhyMjR0ODBwMINgg0CCBIQMjUwEDEB4foh/An5pggACeGCC'
    'RAIwbIJ/AwB/AIN/Fn55disLCjJ6ORhZGVs7GwM7eysaegCCfwEAiEwDT1xggwCCgIMAAwEPc5kz'
    'EzIwMyclCx4bNSl1eG48BGp6e36Efw1fDwMBQGh9f3sqFB0TghUHIQMHAysDJ4ILBQEFAQAEgwAE'
    'AgAgAYIgGQAQAEAABAEEAQgAEAAhAyMDIABAAkQBST+CHwIPA4x/Al9+gn8GAH9tN1dqgn8DAH8A'
    'hH8IfHIKenZub1+CP4Nfgm+CNwd7AX1/AD8AiDMCfwOEAIKAgwABf4lMBgwEQDgGAYIABwECDBBg'
    'AASDDIhMCAwAYHh+f1gmg38EX1Z/A4gAA1AKQJhMC0ADHWlTIAAKUAAMl0wFQUcPHz+CfwhvW3cs'
    'EAhGQYNMB0gDD38AfwCHfwYAfXt2d2+CXw0+fTtdbm8WaxB9AH8AiUwCbB+DAIKAgwACYDyCMwYT'
    'A0E4BgGCAAUDBANwCIMEAhhgggABAYIABwEHTz8PHj6CPAQ6CQwIggSDAwMPfweCAAggAAgkIDEw'
    'MqAzBCAHDwmEEIIIAwAoMKYzEgA/QCVAPnYvd39vfwB7eXZ3b4JfAjw7gn0IPl4uN3sdfACJMwI3'
    'eIMAgoCEAAIDfIVMBkhBBggwQIUAEXB8fzxAMAxDSEwMAHx3P1sSggABAoMABSAQREFI5kwCSECE'
    'QxIDfwsTIyVFCQcDDREJBQFBIQCITAJ/QIQAgoCDAAIfc44zBzIwISYjMDKFMwsBQD8oAQBgDCEw'
    'MvUzBzIBfggECgmCCAhIOAwOMEAgAIgzA3M7B4MAgoCDAAJ4T5lMBEBOQ0n/TA9MA3wgMChEQkFg'
    'AAFBIgCJTAJNfoMAgoCEAAJAP/8zmTMBAIJ+DHR9en9wQCAQCAQCAYMAiDMCP3CEAIKAgwACBzz/'
    'TLRMA3wOAYMAgoCDAAF+/zO3MwF/gwCCgIYAAwEDBoIMBwYDAQABAwaCDAcGAwEAAQMGggwHBgMB'
    'AAEDBoIMBwYDAQABAwaCDAcGAwEAAQMGggwHBgMBAAEDBoIMBwYDAQABAwaCDAcGAwEAAQMGggwH'
    'BgMBAAEDBoIMBwYDAQABAwaCDAcGAwEAAQMGggwHBgMBAAEDBoIMBwYDAQABAwaCDAcGAwEAAQMG'
    'ggwHBgMBAAEDBoIMBwYDAQABAwaCDAcGAwEAAQMGggwHBgMBAAEDBoIMBwYDAQABAwaCDAIGA4YA'
    'AYD/AMAAAYD/AMAAAYCXAI2AyQCHgMsAjICXAIKAlwCDgJcAAYCXAIKA0ACMgMQAh4CXAIKA0ACK'
    'gMYAhoCYAAGA0QCKgLIAhICtAIKA0QCKgJcAhICXAISAlwABgOgAwICXAAGAlwABgNAAwYCuAAGA'
    '0ADBgJcAmICXAI2ArAD/gP+A2oCQAJmAlwCGgP8AowABgP8AwAABgP8AwAABgOYAgoD0AAKAAIeA'
    'zwDLgP8AwQCDgP8AvgCCgIMAA0B4ZIJnhGaCZwFmgmeEZoJnAWaCZ4RmgmcBZoJnhGaCZwFmgmeE'
    'ZoJnAWaCZ4RmgmcBZoJnhGaCZwFmgmeEZoJnAWaCZ4RmgmcBZoJnhGaCZwFmgmeEZoJnAWaCZ4Rm'
    'gmcBZoJnhGaCZwFmgmeEZoJnAWaCZ4RmgmcBZoJnhGaCZwFmgmeEZoJnAWaCZ4RmgmcBZoJnhGaC'
    'ZwFmgmeEZoJnAn5wgwCCgIQAAgd5/xmzGQJ/AYQAgoCDAAE//2aYZgRgB3s/gjsBc4J/BAUKMUSC'
    'AAYYFRMzBQCJZgJ2D4MAgoCDAAJwHv8ZmxkMAH5/Dws0RA4AEBgmgkADQSIAiRkCG3yDAIKAhAAC'
    'AX7/ZphmCQZAfz8CBBkhR4IACBgmAANESDAAiGYCf2CEAIKAgwACD3mMGYIJhwGCIQJhIYlBggnz'
    'GREAfn8/AwYKEiRDAEwyIBARCoIMAQCIGQN5HQODAIKAgwACfGeEZg0AGBwND2cXKQQCAWBhhGCE'
    'ZgtgYWBARwoVajRpSoJUBggSAkIGJupmAQCCfwEDggAPAQJESDATMEgIRTQPYh8AimYBf4MAgoCE'
    'AAJgH6EZgxgDEAMPhH8FfHEUAAnbGQZgH2AVYHmCfwM/TnGCfwh+fTs3V29PM4J7CEU+Xm9zAXwA'
    'iBkDHzhAgwCCgIMAAgMem2YCJgaERgQGZnZmgkICAgCGfwI/PII/g08DXxsegxICREyCCIIQAyBi'
    'IoJCg0aLBoMmn2YDJgZGh2YDRgYmhGYIJgIAfgd4B3iCfwMfJziCP4J/gn4CfT2CWwxnd2ttTkEf'
    'PyB/fQCIZgJ+B4QAgoCDAAF/lBkCGBuDGYIYAQCDfw5tJ2pdMCEBDQwvZwcXbYl/Dz8fByN3VyYL'
    'fiUVHHF6fol/Enw8ORMAEwMBGQRXGCsCVQIAU4MxCnFiQgIIWFl5cVGCYYJBBWFxeHB+jH8JbnB/'
    'D3E/bVtngn8DAH8Ag38DD2dpg2oCayuDKgMrYmiCawlmZ2lsa3gHfwCJGQJZP4MAgoCDAANAeGeK'
    'ZgkmBkI4MEICBiaPZoJkBCQEQGiEfwk3VwNoFRQKDwaCAwQJEEAChWYDZGFggmQMaGBoZGBiYGFg'
    'YWBAggAJPkQJIkAAKkAGi2aDZIRggmGCYgNhRx+Kfwp3TQAPfxgfF34/gn8DAH8AhX8DZxhrgm0D'
    'Dn5/gn4BPYI7CjcvH148fwB/cACIZgNnbnCDAIKAhAACB3mFGQcJQDh2GTBAhAABMIMABAF2eDyC'
    'fAN4cQGDCQkAeH5/RykKFHmDfwNGPAOGAARAEAUQmxkMERABG359eHAKECAhgkEBCZUZiBiJGQYA'
    'B34BfgGFfxZxDj9fb3cHe31+Hl49eXp3b2hXPgEAiBkCfwGEAIKAgwABP4NmBWBGCRBghgACDzCD'
    'QAIgH4QABEAwDg2CBoJ+BnwUVAxEBIMCgwEGQAAQRWBk2mYYYGNAFQAeAil6OzRxDz9/P19vd3t9'
    'fnx9gnsFd2xuXwCJZgJ2D4MAgoCDAAJwHokZghgMEQIMEGQPHw9zDAMYgxkNCQB8fwsaBAFAEAgC'
    'EIIY8BkDGAB/hAALAUIiFAgMEiFBQgCJGQIbfIMAgoCEAAIBfphmCQYAfwUgBEJgZPpmBAF/AQKC'
    'BAMIECCCYIIQAggAiGYCf2CEAIKAgwACD3n/GZsZB0FhISAneQGCAgMECAmCEIJgAQCIGQN5HQOD'
    'AIKAgwACfGf/ZppmAmBjhWIEb2prZ4JlAWOCYgJhYIpmAX+DAIKAhAACYB//GbMZAx84QIMAgoCD'
    'AAMDHib/ZrNmAn4HhACCgP8AvwABgP8AwAABgJcAnYC5AISAzgCMgJcAgoCXAIOArwCHgMsAjIDK'
    'AAGAlwCCgNAAjIDEAIaAmACCgNAAioDGAIaAlwCCgNEAioCXAISAlwCEgP8AAQCKgJcAhICXAISA'
    'lwABgOgAwYCuAAGA0ADBgJcAmIDQAMGAlwCYgAEAsoCdAA==')


class Extasie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='extasie-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decode(self, data):
        f = self.p / 'in.bin'
        f.write_bytes(data)
        r = subprocess.run([str(self.exe), str(f)], capture_output=True)
        return r.returncode, r.stdout

    def pic(self, got, want):
        """Compare only what is on the screen: the format carries no holes."""
        for i in range(0, 8192, 128):
            self.assertEqual(got[i:i + 120], want[i:i + 120], 'row group at %d' % i)

    # -- the stream --------------------------------------------------------
    def test_a_repeat_is_bit_seven_and_a_count(self):
        s = bytes([0x2A]) * (COLS * ROWS) * 2
        rc, out = self.decode(header(rle(s)))
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(s))
        self.pic(out[8192:], page_of(s))

    def test_a_count_of_zero_is_a_hundred_and_twenty_eight(self):
        """Not 256: it is what makes all ten original pictures come out at
        exactly 15,360 bytes."""
        body = b'\x80\x11' * 120                  # 120 runs of 128 = 15,360
        rc, out = self.decode(header(body))
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(bytes([0x11]) * (COLS * ROWS)))

    def test_a_literal_run_copies_the_bytes(self):
        s = bytes(((c * 7 + r) & 0xFF) for c in range(COLS) for r in range(ROWS))
        body = bytearray()
        for i in range(0, len(s), 127):
            chunk = s[i:i + 127]
            body.append(len(chunk))
            body += chunk
        body += b'\x80\x00' * 120                 # the main plane, all zeros
        rc, out = self.decode(header(bytes(body)))
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(s))

    def test_the_two_byte_header_is_skipped(self):
        """It holds the file's own length, and taking it for a record would
        desynchronise everything after it."""
        s = bytes([0x33]) * (COLS * ROWS) * 2
        d = header(rle(s))
        self.assertEqual(d[0] | (d[1] << 8), len(d))
        rc, out = self.decode(d)
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(bytes([0x33]) * (COLS * ROWS)))

    # -- the geometry ------------------------------------------------------
    def test_the_leftmost_column_comes_first(self):
        s = bytearray(COLS * ROWS)
        s[7] = 0x7F
        rc, out = self.decode(header(rle(bytes(s) + bytes(COLS * ROWS))))
        self.assertEqual(rc, 0)
        self.assertEqual(out[addr(7)], 0x7F)
        self.assertEqual(sum(1 for i in range(8192)
                             if (i % 128) < 120 and out[i]), 1)

    def test_the_auxiliary_plane_comes_first(self):
        a = bytes([0x55]) * (COLS * ROWS)
        m = bytes([0x2A]) * (COLS * ROWS)
        rc, out = self.decode(header(rle(a + m)))
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(a))
        self.pic(out[8192:], page_of(m))

    def test_every_visible_byte_is_written(self):
        rc, out = self.decode(header(rle(bytes(COLS * ROWS * 2))))
        self.assertEqual(rc, 0)
        self.assertFalse([i for i in range(8192) if (i % 128) < 120 and out[i]])

    def test_screen_holes_are_left_alone(self):
        rc, out = self.decode(header(rle(bytes(COLS * ROWS * 2))))
        self.assertEqual(rc, 0)
        self.assertTrue(all(out[8192 + i] == 0xEE
                            for i in range(8192) if (i % 128) >= 120))

    # -- truncation --------------------------------------------------------
    def test_a_short_stream_is_refused(self):
        full = header(rle(bytes([0x77]) * (COLS * ROWS * 2)))
        self.assertEqual(self.decode(full[:len(full) // 2])[0], 2)

    def test_an_empty_file_is_refused(self):
        self.assertEqual(self.decode(b'')[0], 2)

    def test_a_stream_one_plane_short_is_refused(self):
        """The main plane is missing: half a picture is not shown as whole."""
        self.assertEqual(self.decode(header(rle(bytes(COLS * ROWS))))[0], 2)

    # -- the real thing ----------------------------------------------------
    def test_a_real_extasie_picture(self):
        """BASTILLE off an original disk: 3,397 bytes for a 15,360-byte
        picture, checked against the rule written out above."""
        s = unrle(BASTILLE)
        self.assertEqual(len(s), COLS * ROWS * 2)
        rc, out = self.decode(BASTILLE)
        self.assertEqual(rc, 0)
        self.pic(out[:8192], page_of(s[:COLS * ROWS]))
        self.pic(out[8192:], page_of(s[COLS * ROWS:]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
