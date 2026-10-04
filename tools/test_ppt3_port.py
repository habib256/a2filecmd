"""The ca65 port of GROUiK's player is the original, byte for byte.

src/plugins/ppt3/original/ppt3.a is French Touch's ACME source (GPLv3),
unmodified. Assembled with ACME at its own origin ($6000) next to a
generated module named rt-frag.pt3 (the demo's music is not in the repo),
it must give exactly the bytes of src/plugins/ppt3/ppt3.s assembled by ca65
WITHOUT PPT3_A2FC, at the same origin, with the same module: every A2FC
change lives behind PPT3_A2FC. Skips when ACME is not installed
(`brew install acme`).

It also counts the guarded sites: each read the player makes through a
pointer derived from the module goes through a MOD_* macro, and no raw
(z80_C) read is left outside the macro definitions.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pt3_fixture import module

ROOT = Path(__file__).resolve().parents[1]
PPT3 = ROOT / 'src/plugins/ppt3'
CFG = '''MEMORY { RAM: file = %O, start = $6000, size = $A000; }
SEGMENTS { CODE: load = RAM, type = rw; }
'''


class Port(unittest.TestCase):
    @unittest.skipUnless(shutil.which('acme') and shutil.which('ca65'), 'needs ACME and ca65')
    def test_byte_identical_to_the_acme_original(self):
        for size in (2048, 16384):
            with self.subTest(module=size), tempfile.TemporaryDirectory(prefix='ppt3-port-') as d:
                t = Path(d)
                shutil.copy(PPT3 / 'original/ppt3.a', t / 'ppt3.a')
                (t / 'rt-frag.pt3').write_bytes(module(size))
                subprocess.run(['acme', '--format', 'plain', '--outfile', 'acme.bin', 'ppt3.a'],
                               cwd=t, check=True, capture_output=True)
                (t / 'faithful.cfg').write_text(CFG)
                subprocess.run(['ca65', '-o', 'port.o', '-I', str(t), str(PPT3 / 'ppt3.s')],
                               cwd=t, check=True, capture_output=True)
                subprocess.run(['ld65', '-C', 'faithful.cfg', '-o', 'port.bin', 'port.o'],
                               cwd=t, check=True, capture_output=True)
                acme, port = (t / 'acme.bin').read_bytes(), (t / 'port.bin').read_bytes()
                self.assertEqual(len(port), len(acme))
                self.assertEqual(port, acme)

    def test_original_is_vendored_unmodified(self):
        text = (PPT3 / 'original/ppt3.a').read_text()
        self.assertIn('by GROUiK/FRENCH TOUCH - 2019', text)
        self.assertIn('!bin "rt-frag.pt3"', text)
        self.assertTrue((PPT3 / 'original/License.txt').read_text().count('GNU GENERAL PUBLIC LICENSE'))
        self.assertFalse((PPT3 / 'original/rt-frag.pt3').exists(), 'the demo music stays out of the repo')

    def test_every_module_read_is_guarded(self):
        text = (PPT3 / 'ppt3.s').read_text()
        body = re.sub(r'\.macro.*?\.endmacro', '', text, flags=re.S)
        code = [l.split(';')[0] for l in body.splitlines()]
        counts = {m: sum(l.split() == [m] for l in code) for m in ('MOD_LDA_C', 'MOD_LDA_L', 'MOD_LDA_IX', 'MOD_ADC_L')}
        self.assertEqual(counts, {'MOD_LDA_C': 21, 'MOD_LDA_L': 21, 'MOD_LDA_IX': 5, 'MOD_ADC_L': 1})
        self.assertFalse([l for l in code if re.search(r'\(z80_C\)', l)], 'unguarded pattern read')
        # (z80_IX),Y reads after INIT point at ChanA/B/C; the remaining raw
        # (z80_L)/(z80_E) reads are the player's own tables (NT_DATA, T_,
        # NT_, VT_, SPCCOMS, AddToEn, AYREGS, and in A2FC the ZX note table
        # INIT copies, picked by X = 0-7): 15 + 2 sites, counted here so
        # that a new one cannot appear unnoticed.
        raw_l = [l for l in code if re.search(r'\b(LDA|ADC|ORA)\s+\(z80_L\)', l)]
        raw_e = [l for l in code if re.search(r'\bLDA\s+\(z80_E\)', l)]
        self.assertEqual((len(raw_l), len(raw_e)), (17, 2))


if __name__ == '__main__':
    unittest.main()
