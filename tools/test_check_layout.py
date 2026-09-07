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
                      __MAIN_FILEOFFS__=0x1000, __MAIN_START__=0x4000,
                      __MAIN_LAST__=0xBCC5, __LC_START__=0xD400, __LC_LAST__=0xE000,
                      __LOWEXE_RUN__=0x1C00, __LOWEXE_SIZE__=0x2A0,
                      __LOWBSS_RUN__=0x1058, __LOWBSS_SIZE__=0x953,
                      __HIMEM__=0xBF00, __STACKSIZE__=0x100,
                      __ONCE_RUN__=0xBBCB, __BSS_RUN__=0x1000, __BSS_SIZE__=0x58)
        self.loader = dict(LC_STAGE=0x1000, LC_BYTES=0xC00, CODE_ADDR=0x4000,
                           STAGE_BYTES=0x1000)
        self.length = 0x1000 + 0xBCC5 - 0x4000

    def check(self):
        return check_layout(self.s, self.loader, self.length)

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
        self.s['__LOWEXE_RUN__'] = 0x2100
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

    def test_low_code_must_sit_above_the_lc_image_and_below_the_prefix(self):
        self.s['__LOWEXE_RUN__'] = 0x1800
        self.assertIn('LOWEXE starts inside the LC staging area', self.check())
        self.s['__LOWEXE_RUN__'] = 0x1C00
        self.s['__LOWEXE_SIZE__'] = 0x401
        self.assertIn('LOWEXE runs past the staged prefix', self.check())

    def test_low_bss_may_not_climb_into_the_low_code(self):
        self.s['__LOWBSS_SIZE__'] = 0xC00                     # jusqu'en $1C57
        self.assertIn('low BSS runs into LOWEXE', self.check())


if __name__ == '__main__':
    unittest.main()
