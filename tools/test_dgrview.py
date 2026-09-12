"""Run DGRVIEW's actual code: where each lo-res pixel lands in the text page.

Double lo-res is the mode whose memory is the text page, split between two
banks and two nibbles per byte, so the whole of this overlay is address
arithmetic. These tests pin that arithmetic against the Apple II layout: the
three thirds of eight rows $80 apart, the even columns in the auxiliary
bank, the low nibble above the high one.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
unsigned char host_main[1024], host_aux[1024], host_stage[2049];
unsigned char host_bank, host_shown;
#include "src/plugins/dgrview.c"

static char host_input[17];
static char host_note[80], host_reselect[17];
static struct Entry host_sel;
static unsigned char prompt_ok = 1;

static unsigned char mock_prompt(const char* label, const char* init, unsigned char hex)
{ (void)label; (void)init; (void)hex; return prompt_ok; }
static char mock_cgetc(void) { return KEY_ESC; }

int main(int argc, char** argv)
{
    static struct A2fcApi api;
    int i;
    /* argv: file type width_or_dash */
    strcpy(host_sel.name, "PIC");
    host_sel.type = (unsigned char)atoi(argv[2]);
    if (argv[3][0] == '-') prompt_ok = 0; else strcpy(host_input, argv[3]);
    if (argc > 4) host_sel.aux = (unsigned int)strtoul(argv[4], 0, 10);
    host_note[0] = 0;
    memset(host_stage, 0xA5, sizeof(host_stage)); /* stale previous file */
    if (argc > 5 && atoi(argv[5])) {
        for (i = 0; i < 1024; ++i) {
            host_aux[i] = (unsigned char)(i * 3 + 1);
            host_main[i] = (unsigned char)(i * 5 + 2);
        }
    }

    api.selected = &host_sel;
    api.full = argv[1];
    api.note = host_note; api.reselect = host_reselect; api.input = host_input;
    api.fopen = fopen; api.fread = fread; api.fclose = fclose;
    api.strcpy = strcpy; api.sprintf = sprintf;
    api.version=4;api.media_wait=mock_cgetc;api.prompt = mock_prompt; api.cgetc = mock_cgetc;

    plugin_entry(&api);
    printf("%u|%u|%s\n", host_shown, wide, host_note);
    for (i = 0; i < 1024; ++i) fputc(host_aux[i], stderr);
    for (i = 0; i < 1024; ++i) fputc(host_main[i], stderr);
    return 0;
}
'''


def row_of(r):
    """The Apple II text-page offset of byte row r, 0..23."""
    return (r & 7) * 128 + (r >> 3) * 40


class DgrView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dgrview-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def view(self, data, ftype=6, width='--', aux=0, seeded=False):
        f = self.p / 'pic'
        f.write_bytes(data)
        r = subprocess.run([str(self.exe), str(f), str(ftype), width, str(aux), str(int(seeded))],
                           capture_output=True, check=True)
        self.assertEqual(f.read_bytes(), data)
        self.assertEqual(len(r.stderr), 2048)
        shown, wide, note = r.stdout.decode().strip().split('|', 2)
        return int(shown), int(wide), note, r.stderr[:1024], r.stderr[1024:2048]

    # -- whole screens ----------------------------------------------------
    def test_a_double_screen_fills_the_auxiliary_half_first(self):
        aux_half = bytes((i * 3) & 0xFF for i in range(1024))
        main_half = bytes((i * 5 + 1) & 0xFF for i in range(1024))
        shown, wide, note, aux, main = self.view(aux_half + main_half)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        self.assertEqual(aux, aux_half)
        self.assertEqual(main, main_half)

    def test_a_single_screen_is_forty_columns_in_the_main_half(self):
        page = bytes((i * 7) & 0xFF for i in range(1024))
        shown, wide, note, aux, main = self.view(page)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(main, page)
        self.assertEqual(aux, bytes(1024))          # untouched: 80COL is off

    def test_too_big_is_refused(self):
        shown, _, note, _, _ = self.view(bytes(2049))
        self.assertEqual(shown, 0)
        self.assertIn('Over 2048', note)

    def test_an_empty_file_is_refused(self):
        shown, _, note, _, _ = self.view(b'')
        self.assertEqual(shown, 0)
        self.assertIn('Over 2048', note)

    def test_a_directory_is_refused(self):
        shown, _, note, _, _ = self.view(bytes(1024), ftype=0x0F)
        self.assertEqual(shown, 0)
        self.assertIn('Select', note)

    # -- a2dgrx pixmaps ---------------------------------------------------
    def pixel(self, aux, main, x, y):
        """The colour of double lo-res pixel (x, y), read back out of the two
        halves the way the hardware would."""
        page = aux if not (x & 1) else main
        b = page[row_of(y >> 1) + (x >> 1)]
        return (b >> 4) if (y & 1) else (b & 0x0F)

    def test_a_pixmap_lands_where_its_mask_says(self):
        """4x2, the second row transparent. Its colour nibbles are NOT zero:
        a transparent pixel painted anyway would show, which is the whole
        point of the mask, and zeros would have hidden the mistake."""
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4,
                      0x07, 0x08, 0x09, 0x0A])
        shown, wide, note, aux, main = self.view(data, width='04')
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('4 x 2', note)
        x0, y0 = (80 - 4) // 2, (48 - 2) // 2
        for i in range(4):
            self.assertEqual(self.pixel(aux, main, x0 + i, y0), i + 1)
            self.assertEqual(self.pixel(aux, main, x0 + i, y0 + 1), 0)  # masked out
        # and nothing else on the screen was painted
        lit = [(x, y) for y in range(48) for x in range(80)
               if self.pixel(aux, main, x, y)]
        self.assertEqual(lit, [(x0 + i, y0) for i in range(4)])

    def test_both_banks_and_both_nibbles_are_reached(self):
        """A 2x2 block proves the even/odd bank split and the low/high nibble
        split at once."""
        data = bytes([0xF5, 0xF6, 0xF7, 0xF8])
        shown, _, _, aux, main = self.view(data, width='02')
        x0, y0 = (80 - 2) // 2, (48 - 2) // 2
        self.assertEqual(self.pixel(aux, main, x0, y0), 5)
        self.assertEqual(self.pixel(aux, main, x0 + 1, y0), 6)
        self.assertEqual(self.pixel(aux, main, x0, y0 + 1), 7)
        self.assertEqual(self.pixel(aux, main, x0 + 1, y0 + 1), 8)
        self.assertNotEqual(x0 & 1, (x0 + 1) & 1)    # the two really differ in bank

    def test_the_widest_pixmap_reaches_both_edges(self):
        """80 wide is the whole screen across; 2,048 bytes is all this reads,
        so 80 x 25 is the tallest that fits. Both corners must be lit."""
        data = bytes([0xF9] * (80 * 25))
        shown, _, note, aux, main = self.view(data, width='50')     # $50 = 80
        self.assertEqual(shown, 1)
        self.assertIn('80 x 25', note)
        y0 = (48 - 25) // 2
        self.assertEqual(self.pixel(aux, main, 0, y0), 9)           # left, aux bank
        self.assertEqual(self.pixel(aux, main, 79, y0 + 24), 9)     # right, main bank
        lit = sum(1 for y in range(48) for x in range(80) if self.pixel(aux, main, x, y))
        self.assertEqual(lit, 80 * 25)

    def test_a_pixmap_over_2048_bytes_is_refused(self):
        """Only 2,048 bytes are read, so a bigger sprite cannot be shown at
        all rather than shown truncated."""
        shown, _, note, _, _ = self.view(bytes([0xF1] * 3000), width='50')
        self.assertEqual(shown, 0)
        self.assertIn('Over 2048', note)

    def test_a_width_that_does_not_divide_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * 100), width='07')
        self.assertEqual(shown, 0)
        self.assertIn('Invalid sprite', note)

    def test_a_width_over_eighty_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * 81), width='51')
        self.assertEqual(shown, 0)

    def test_a_pixmap_taller_than_the_screen_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * (2 * 49)), width='02')
        self.assertEqual(shown, 0)
        self.assertIn('Invalid sprite', note)

    def test_declining_the_width_shows_nothing(self):
        shown, _, _, aux, main = self.view(bytes([0xF1] * 12), width='-')
        self.assertEqual(shown, 0)
        self.assertEqual(sum(aux) + sum(main), 0)

    def test_auxtype_0400_is_what_says_lo_res(self):
        """bmp2dhr writes .SLO at 962 bytes, not 1024: an equality test on the
        size would refuse the very files this is for."""
        page = bytes((i * 11 + 3) & 0xFF for i in range(962))
        shown, wide, note, aux, main = self.view(page, aux=0x0400)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(main[:962], page)
        self.assertEqual(main[962:], bytes(1024 - 962))     # the rest stays black

    def test_a_double_file_of_an_odd_size_splits_in_two(self):
        """.DLO is 1,922 bytes: two halves of 961."""
        d = bytes((i * 13 + 7) & 0xFF for i in range(1922))
        shown, wide, note, aux, main = self.view(d, aux=0x0400)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        self.assertEqual(aux[:961], d[:961])
        self.assertEqual(main[:961], d[961:])

    def test_the_proposed_header_says_what_the_file_is(self):
        """'DGR' 1, width, height, flags -- rows of forty bytes with no screen
        holes, so each row lands at its own address."""
        lines = 24
        auxhalf = bytes((i * 3 + 1) & 0xFF for i in range(40 * lines))
        mainhalf = bytes((i * 5 + 2) & 0xFF for i in range(40 * lines))
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 80, 48, 1, 0])
        shown, wide, note, aux, main = self.view(hdr + auxhalf + mainhalf)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        for r in range(lines):
            at = row_of(r)
            self.assertEqual(aux[at:at + 40], auxhalf[r * 40:(r + 1) * 40])
            self.assertEqual(main[at:at + 40], mainhalf[r * 40:(r + 1) * 40])
        # the screen holes are left alone, which is the point of the format:
        # rows 0, 8 and 16 fill offsets 0-119 and 120-127 is the first hole
        self.assertEqual(aux[120:128], bytes(8))
        self.assertEqual(main[120:128], bytes(8))

    def test_the_proposed_header_single_half(self):
        lines = 24
        onehalf = bytes((i * 7 + 4) & 0xFF for i in range(40 * lines))
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 40, 48, 0, 0])
        shown, wide, note, aux, main = self.view(hdr + onehalf)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(main[row_of(23):row_of(23) + 40], onehalf[23 * 40:24 * 40])
        self.assertEqual(aux, bytes(1024))

    def test_a_header_asking_for_more_than_the_screen_is_refused(self):
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 200, 48, 1, 0])
        shown, _, note, _, _ = self.view(hdr + bytes(1920))
        self.assertEqual(shown, 0)
        self.assertIn('Invalid or truncated', note)

    def assert_seeded_banks(self, aux, main):
        self.assertEqual(aux, bytes((i * 3 + 1) & 255 for i in range(1024)))
        self.assertEqual(main, bytes((i * 5 + 2) & 255 for i in range(1024)))

    def test_sprite_height_boundary(self):
        shown, _, note, aux, main = self.view(bytes([0xF1]) * 48, width='01')
        self.assertEqual(shown, 1)
        self.assertIn('1 x 48', note)
        for y in range(48):
            self.assertEqual(self.pixel(aux, main, 39, y), 1)
        shown, _, note, aux, main = self.view(bytes([0xF1]) * 49,
                                             width='01', seeded=True)
        self.assertEqual(shown, 0)
        self.assert_seeded_banks(aux, main)

    def test_extra_payload_is_refused(self):
        data = b'DGR\x01\x28\x30\0\0' + bytes(961)
        shown, _, note, aux, main = self.view(data, seeded=True)
        self.assertEqual(shown, 0)
        self.assertIn('Invalid or truncated', note)
        self.assert_seeded_banks(aux, main)

    def test_truncated_header_and_payload_never_touch_screen_banks(self):
        data = b'DGR\x01\x50\x30\x01\0' + bytes([0x55]) * 1920
        for cut in (*range(3, 10), 255, 968, 1024, 1927):
            with self.subTest(cut=cut):
                shown, _, note, aux, main = self.view(data[:cut], width='01', seeded=True)
                self.assertEqual(shown, 0)
                self.assertIn('Invalid or truncated', note)
                self.assert_seeded_banks(aux, main)

    def test_invalid_header_fields_are_not_interpreted_as_sprites(self):
        data = bytearray(b'DGR\x01\x50\x30\x01\0' + bytes(1920))
        for at, value in ((3, 2), (4, 0), (4, 40), (5, 0), (5, 47), (6, 2), (7, 1)):
            with self.subTest(at=at, value=value):
                mutated = data.copy(); mutated[at] = value
                shown, _, note, aux, main = self.view(mutated, width='01', seeded=True)
                self.assertEqual(shown, 0)
                self.assert_seeded_banks(aux, main)

    def test_sprite_height_is_checked_before_narrowing_to_a_byte(self):
        for size, width in ((255, '01'), (256, '01'), (257, '01'), (304, '01'),
                            (305, '01'), (1536, '03')):
            with self.subTest(size=size):
                shown, _, note, aux, main = self.view(bytes([0xF1]) * size, width=width, seeded=True)
                self.assertEqual(shown, 0)
                self.assertIn('Invalid sprite', note)
                self.assert_seeded_banks(aux, main)

    def test_a_small_file_without_the_auxtype_is_still_a_pixmap(self):
        """The auxtype is what distinguishes a short screen from a sprite."""
        shown, _, note, _, _ = self.view(bytes([0xF1] * 12), width='04')
        self.assertEqual(shown, 1)
        self.assertIn('pixmap', note)


if __name__ == '__main__':
    unittest.main()
