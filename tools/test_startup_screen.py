"""The title page stays on the screen for the whole first loading.

A2FILE.SYSTEM (src/loader.c) draws it, then loads A2FILE.CODE; A2FC's
main() then reads the configuration and both panels, writing only
"Reading directory..." on row 21, and draws the panels last. Nothing may
clear the screen before that: not clrscr, and not videomode, which calls
the 80-column firmware at $C300 (a PR#3, which clears it). No emulator
runs here, so this holds the source to it; activity_begin's writes are
checked on the real assembly by tools/test_display.py (row 21 only).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()


def startup():
    """main() of a2fc.c up to its first draw_all()."""
    start = SOURCE.index('\nint main(void)\n{')
    return SOURCE[start:SOURCE.index('draw_all();', start)]


class StartupScreen(unittest.TestCase):
    def test_nothing_clears_the_title_page_before_the_panels(self):
        code = re.sub(r'/\*.*?\*/', '', startup(), flags=re.S)
        for call in ('clrscr(', 'cclear(', 'clear_row(', 'message(', 'bar_begin(', 'keys_bar('):
            self.assertNotIn(call, code)
        calls = re.findall(r'[^\n]*videomode\([^\n]*', code)
        self.assertEqual(len(calls), 1, calls)
        # only when 80 columns (RD80VID) and 80STORE (RD80STORE) are not on
        self.assertIn('0xC01F', calls[0])
        self.assertIn('0xC018', calls[0])
        self.assertTrue(calls[0].strip().startswith('if (!('), calls[0])

    def test_the_panels_come_after_both_reads_and_the_pause(self):
        code = startup()
        self.assertLess(code.index('read_panel(0);'), code.index('read_panel(1);'))
        self.assertLess(code.index('read_panel(1);'), code.index('key_wait(3)'))

    def test_the_launcher_draws_the_page_before_loading(self):
        loader = (ROOT / 'src/loader.c').read_text()
        main = loader[loader.index('int main(void)'):]
        self.assertLess(main.index('videomode(VIDEOMODE_80COL);'), main.index('clrscr();'))
        self.assertLess(main.index('Loading A2FILE.CODE'), main.index('fopen(CODE_FILE'))
        self.assertEqual(main.count('clrscr();'), 1)


if __name__ == '__main__':
    unittest.main()
