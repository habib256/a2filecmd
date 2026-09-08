"""Les controles de disposition, sans compiler quoi que ce soit.

    python3 -m unittest discover -s tools -p 'test_*.py'
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_layout import check_layout


class SplitLoadLayout(unittest.TestCase):
    def setUp(self):
        # Une disposition saine, celle que produit le lien.
        self.s = dict(__LCIMAGE_FILEOFFS__=0, __LCIMAGE_START__=0x1000,
                      __LCIMAGE_SIZE__=0xC00, __LCIMAGE_LAST__=0x1C00,
                      __MAIN_FILEOFFS__=0xC00, __MAIN_START__=0x4000,
                      __MAIN_LAST__=0xBCC5, __LC_START__=0xD400, __LC_LAST__=0xE000,
                      __LOWRAM_START__=0x1000, __LOWRAM_SIZE__=0xB00,
                      __IMAGE_START__=0x1B00, __IMAGE_LAST__=0x1F60,
                      __HELP_START__=0x1B00, __HELP_LAST__=0x1EE0,
                      __TEXT_START__=0x1B00, __TEXT_LAST__=0x1D80,
                      __HEX_START__=0x1B00, __HEX_LAST__=0x1DF0,
                      __DELETE_START__=0x1B00, __DELETE_LAST__=0x1E00,
                      __LOWBSS_RUN__=0x1058, __LOWBSS_SIZE__=0x953,
                      __HIMEM__=0xBF00, __STACKSIZE__=0x100,
                      __ONCE_RUN__=0xBBCB, __BSS_RUN__=0x1000, __BSS_SIZE__=0x58)
        self.loader = dict(LC_STAGE=0x1000, LC_BYTES=0xC00, CODE_ADDR=0x4000,
                           STAGE_BYTES=0xC00)
        self.length = 0xC00 + 0xBCC5 - 0x4000
        self.overlays = dict(IMAGE=0x1F60 - 0x1B00, HELP=0x1EE0 - 0x1B00, TEXT=0x280,
                             HEX=0x2F0, DELETE=0x300, MUSIC=0x200, RUN=0x200, ATTR=0x300,
                             EDIT=0xC00, MENU=0x600, DISKIMG=0x900, IMGFS=0x300, DOS33=0x400, UNSHRINK=0x600, BASLIST=0x340, COMPARE=0x200, SEARCH=0x200, BINARY2=0x300)
        for name in ('MUSIC', 'RUN', 'ATTR', 'EDIT', 'MENU', 'DISKIMG', 'IMGFS', 'DOS33', 'UNSHRINK', 'BASLIST', 'COMPARE', 'SEARCH', 'BINARY2'):
            self.s['__%s_START__' % name] = 0x1B00
            self.s['__%s_LAST__' % name] = 0x1B00 + self.overlays[name]
        for name in ('IMAGE', 'TEXT', 'HEX', 'DELETE', 'HELP', 'MUSIC', 'RUN', 'ATTR', 'EDIT', 'MENU', 'DISKIMG', 'IMGFS', 'DOS33', 'UNSHRINK', 'BASLIST', 'COMPARE', 'SEARCH', 'BINARY2'):
            # the RO segment ends where the file ends
            self.s['__%sRO_LAST__' % name] = self.s['__%s_START__' % name] + self.overlays[name]
            self.s['__%s_LAST__' % name] = self.s['__%s_START__' % name]

    def check(self):
        return check_layout(self.s, self.loader, self.length, self.overlays)

    def test_valid(self):
        self.assertEqual(self.check(), [])

    def test_loader_disagreement(self):
        for key in self.loader:
            with self.subTest(key=key):
                self.loader[key] += 1
                self.assertTrue(self.check())
                self.loader[key] -= 1

    def test_wrong_file_offsets_and_length(self):
        for key in ('__LCIMAGE_FILEOFFS__', '__MAIN_FILEOFFS__'):
            self.s[key] += 1
            self.assertTrue(self.check())
            self.s[key] -= 1
        for delta in (-1, 1):
            self.assertTrue(check_layout(self.s, self.loader, self.length + delta))

    def test_stage_overlaps_the_graphics_page(self):
        self.loader['LC_STAGE'] = self.s['__LCIMAGE_START__'] = 0x1500
        self.s['__LCIMAGE_LAST__'] = 0x2100
        self.assertIn('staging overlaps the ProDOS buffers or the graphics page', self.check())

    def test_main_and_bank_overflow(self):
        self.s['__MAIN_LAST__'] = 0xBF01
        self.assertTrue(self.check())
        self.s['__MAIN_LAST__'] = 0xBCC5
        self.s['__LC_LAST__'] = 0xE001
        self.s['__LCIMAGE_LAST__'] = 0x1C01
        self.assertTrue(self.check())

    def test_cold_end_must_stay_under_the_c_stack(self):
        """Le piege silencieux de ld65 : une zone BSS de taille negative."""
        self.s['__ONCE_RUN__'] = 0xBE01                       # $BF00 - $100 + 1
        self.assertTrue(any('C stack' in e for e in self.check()))

    def test_bss_alone_may_not_reach_the_stack(self):
        self.s['__BSS_RUN__'] = 0xBDF0
        self.assertTrue(any('BSS' in e for e in self.check()))

    def test_overlay_between_low_ram_and_graphics_page(self):
        self.s['__IMAGE_START__'] = 0x1A00
        self.assertIn('IMAGE overlay starts inside the low RAM', self.check())
        self.s['__IMAGE_START__'] = 0x1B00
        self.s['__IMAGERO_LAST__'] = 0x2001
        self.assertIn('IMAGE overlay runs past $2000', self.check())

    def test_overlay_file_must_be_as_long_as_the_link_says(self):
        self.overlays['IMAGE'] += 1
        self.assertIn('IMAGE overlay file length does not match the link', self.check())
        self.overlays['IMAGE'] = None                         # fichier absent
        self.assertIn('IMAGE overlay file length does not match the link', self.check())
        self.assertEqual(check_layout(self.s, self.loader, self.length), [])

    def test_low_bss_may_not_climb_into_the_overlay_window(self):
        self.s['__LOWBSS_SIZE__'] = 0xB00                     # jusqu'en $1B57
        self.assertIn('low BSS runs into the overlay window', self.check())

    def test_the_loader_needs_32_bytes_under_bf00(self):
        # loader.c tient sa pile C en $BF00 et lit A2FILE.CODE jusqu'a __MAIN_LAST__ :
        # a $BEE1 le dernier fread ecraserait son propre cadre.
        self.s['__MAIN_LAST__'] = 0xBEE0
        self.length = 0xC00 + 0xBEE0 - 0x4000
        self.assertEqual(self.check(), [])
        self.s['__MAIN_LAST__'] = 0xBEE1
        self.length = 0xC00 + 0xBEE1 - 0x4000
        self.assertTrue(any('loader stack' in e for e in self.check()), self.check())


if __name__ == '__main__':
    unittest.main()
