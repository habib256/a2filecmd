"""Les fichiers de demonstration doivent se relire comme A2 File Cmd les lit.

Le decodeur ci-dessous est la transcription de decode_rle() dans src/a2fc.c :
si l'aller-retour passe ici, la disquette montrera bien l'image.

    python3 tools/test_mkdemo.py
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import mkdemo


def decode(stream, size):
    """La boucle de a2fc.c : $80|n-3 puis l'octet a repeter, sinon n-1 litteraux."""
    out, i = bytearray(), 8
    while len(out) < size:
        t = stream[i]; i += 1
        if t & 0x80:
            out += bytes((stream[i],)) * ((t & 0x7F) + 3); i += 1
        else:
            out += stream[i:i + t + 1]; i += t + 1
    assert i == len(stream), 'le flux doit finir avec la derniere ligne'
    return bytes(out)


class Demo(unittest.TestCase):
    def test_hgr_card_roundtrips(self):
        raw = mkdemo.hgr_card()
        self.assertEqual(len(raw), 8192)
        f = mkdemo.image(b'HGRR', 8192, raw)
        self.assertEqual(f[:8], b'HGRR\x01\x00\x00\x20')
        self.assertEqual(decode(f, 8192), raw)

    def test_dhgr_card_roundtrips(self):
        raw = mkdemo.dhgr_card()
        self.assertEqual(len(raw), 16384)
        f = mkdemo.image(b'DHRR', 16384, raw)
        self.assertEqual(f[:8], b'DHRR\x01\x00\x00\x40')
        self.assertEqual(decode(f, 16384), raw)

    def test_rle_survives_awkward_inputs(self):
        for data in (b'', b'\x00', b'\x01\x02\x03', b'\xff' * 1000,
                     bytes(range(256)) * 3, b'\x00' * 130 + b'\x01' * 3,
                     bytes([i // 4 for i in range(600)])):
            with self.subTest(n=len(data)):
                out, i = bytearray(), 0
                stream = mkdemo.rle(data)
                while i < len(stream):
                    t = stream[i]; i += 1
                    if t & 0x80:
                        out += bytes((stream[i],)) * ((t & 0x7F) + 3); i += 1
                    else:
                        out += stream[i:i + t + 1]; i += t + 1
                self.assertEqual(bytes(out), data)

    def test_music_is_an_mb1_stream_that_ends(self):
        mb = mkdemo.fanfare()
        self.assertEqual(mb[:3], b'MB1')
        self.assertEqual(mb[6:8], b'\x08\x00', "le flux commence apres 8 octets d'en-tete")
        self.assertEqual(len(mb) - 8, int.from_bytes(mb[4:6], 'little'))
        # a2fc.c refuse un flux dont le dernier paquet n'est pas un END ($Ex)
        self.assertEqual(mb[-1] & 0xF0, 0xE0)
        self.assertLess(len(mb), 2304, 'MUSIC_ZONE : 2304 octets au plus')

    def test_applesoft_program_is_well_formed(self):
        prog = mkdemo.applesoft([(10, bytes([mkdemo.HOME])), (20, bytes([mkdemo.END]))])
        self.assertEqual(prog[-2:], b'\x00\x00')
        link = int.from_bytes(prog[0:2], 'little')
        self.assertEqual(link, 0x0801 + 6, 'le chainage pointe la ligne suivante')


if __name__ == '__main__':
    unittest.main()
