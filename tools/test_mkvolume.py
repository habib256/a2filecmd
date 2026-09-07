"""L'aller-retour du constructeur de volume : ce qu'on met, on le relit.

    python3 tools/test_mkvolume.py
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image, BLOCK


def build(stage, **kw):
    out = stage.parent / 'test.po'
    cmd = [sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(out),
           '--volume', kw.get('volume', 'TESTVOL'), '--blocks', str(kw.get('blocks', 280))]
    if kw.get('boot'):
        cmd += ['--boot', str(kw['boot'])]
    subprocess.run(cmd, check=True, capture_output=True)
    return Image(out.read_bytes()), out


class Roundtrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stage = Path(self.tmp.name) / 'vol'
        (self.stage / 'SUB').mkdir(parents=True)
        # graine (<= 1 bloc), pousse (index + blocs), et un sous-repertoire
        (self.stage / 'SMALL.TXT').write_bytes(b'hello\r')
        self.big = bytes(range(256)) * 40                      # 10 240 octets
        (self.stage / 'BIG.BIN').write_bytes(self.big)
        (self.stage / 'BOOTER.SYS').write_bytes(b'\x4c\x00\x20' * 100)
        (self.stage / 'SUB' / 'DEEP.TXT').write_bytes(b'deep\r')
        (self.stage / 'SUB' / 'TYPED#FC0801').write_bytes(b'\x00\x01\x02')

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_and_layout(self):
        img, _ = build(self.stage)
        h = img.header()
        self.assertEqual(h['name'], 'TESTVOL')
        self.assertEqual(h['blocks'], 280)
        self.assertEqual(h['bitmap'], 6)
        self.assertEqual(h['files'], 4)          # SMALL BIG BOOTER SUB

    def test_files_come_back_byte_for_byte(self):
        img, _ = build(self.stage)
        got = {name: (kind, size) for name, kind, size in img.walk()}
        self.assertEqual(got['/SMALL'], ('TXT', 6))
        self.assertEqual(got['/BIG'], ('BIN', len(self.big)))
        self.assertEqual(got['/BOOTER'], ('SYS', 300))
        self.assertEqual(got['/SUB'], ('DIR', 0))
        self.assertEqual(got['/SUB/DEEP'], ('TXT', 5))
        self.assertEqual(got['/SUB/TYPED'], ('BAS', 3))
        for e in img.entries(2):
            if e[1:4] == b'BIG':
                self.assertEqual(img.read(e), self.big, 'un sapling doit se relire entier')

    def test_aux_type_from_the_host_name(self):
        img, _ = build(self.stage)
        sub = next(e for e in img.entries(2) if e[1:4] == b'SUB')
        typed = next(e for e in img.entries(int.from_bytes(sub[0x11:0x13], 'little'))
                     if e[1:6] == b'TYPED')
        self.assertEqual(int.from_bytes(typed[0x1F:0x21], 'little'), 0x0801)

    def test_bitmap_matches_what_was_written(self):
        img, out = build(self.stage)
        used = 280 - img.free_blocks()
        # tout ce qui est marque occupe doit l'etre pour une raison : amorce,
        # repertoire, table, puis exactement les blocs des fichiers
        expected = 2 + 4 + 1
        for e in img.entries(2):
            expected += int.from_bytes(e[0x13:0x15], 'little')
        for name, kind, size in img.walk():
            if kind == 'DIR':
                key = None
        sub = next(e for e in img.entries(2) if e[1:4] == b'SUB')
        for e in img.entries(int.from_bytes(sub[0x11:0x13], 'little')):
            expected += int.from_bytes(e[0x13:0x15], 'little')
        self.assertEqual(used, expected)

    def test_boot_blocks_are_copied(self):
        boot = Path(self.tmp.name) / 'boot.tmpl'
        boot.write_bytes(bytes(range(256)) * 4)
        img, _ = build(self.stage, boot=boot)
        self.assertEqual(img.d[:1024], boot.read_bytes())

    def test_refuses_what_it_cannot_write(self):
        (self.stage / 'nom impossible.txt').write_bytes(b'x')
        with self.assertRaises(subprocess.CalledProcessError):
            build(self.stage)
        (self.stage / 'nom impossible.txt').unlink()
        (self.stage / 'HUGE.BIN').write_bytes(bytes(200 * 1024))
        with self.assertRaises(subprocess.CalledProcessError):
            build(self.stage)


if __name__ == '__main__':
    unittest.main()
