"""pt3_lib's three defects, fixed 2026-10-03, on the real decoder (sim65, both CPUs).

Found by tools/pt3_compare.py against GROUiK's player (Bulba's semantics):
  - a pattern was always cut at row 64: Vortex Tracker patterns can be
    longer, and such songs ended early or played the wrong rows;
  - a sample's envelope offset was added unsigned: -16 on a period of $40
    gave $130 instead of $30;
  - the on/off effect never cut the channel: the non-zero-page build
    reloaded its countdown instead of storing it;
  - (found on the way) a negative envelope offset came out one too small,
    the slide-down path keeping a BCS's carry; and an amplitude slide going
    up from -1 to 0 fell into the slide-down code and left the amplitude
    at 0 for that tick (DR.DISMALAC.PT3, FOXXRAIN281.PT3).
Each module below exercises one of them; pt3_lib (without its clock
conversion) must give the 14 registers GROUiK's engine gives with the same
ZX note table, frame for frame, and the specific values are checked too.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt3_sim
from pt3_compare import zx_table
from pt3_fixture import module

PATTERNS = (1040, 1280, 1791)


def ay(r):
    """What the AY keeps: 12-bit tones, 5-bit noise (GROUiK's raw AYREGS
    carry the player's unmasked bytes; both conversions mask first)."""
    r = bytearray(r)
    for i in (1, 3, 5):
        r[i] &= 15
    r[6] &= 31
    return bytes(r)


def song(rows_a, rows_b, rows_c, speed=1, sample=None):
    """module(2048) with explicit pattern bytes (row skip 1 and sample 1
    first: before any sample command the players differ by design).
    All three channels must last as many rows: the two players end a
    pattern on different conditions otherwise (channel A's end marker,
    all three end markers)."""
    b = bytearray(module(2048, speed=speed))
    table = b[103] | b[104] << 8
    for ch, data in enumerate((rows_a, rows_b, rows_c)):
        start = PATTERNS[ch]
        body = bytes([0xB1, 0x01, 0xD1]) + bytes(data) + b'\0'   # skip 1, sample 1
        b[start:start + len(body)] = body
        b[table + 2 * ch:table + 2 * ch + 2] = start.to_bytes(2, 'little')
    if sample is not None:
        b[766:766 + len(sample)] = sample
    return bytes(b)


@unittest.skipUnless(ppt3_sim.available(), 'needs cc65 and sim65')
class Pt3libFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory(prefix='pt3-fixes-')
        cls.grouik = ppt3_sim.Grouik(cls.tmpdir.name)
        cls.libs = {cpu: ppt3_sim.Pt3lib(cls.tmpdir.name, cpu, converted=False) for cpu in ('6502', '65c02')}

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def both(self, data, frames):
        g = self.grouik.run(data, frames, note_table=zx_table(data))
        for cpu, lib in self.libs.items():
            p = lib.run(data, frames)
            n = min(len(g), len(p))
            for i in range(1, n):
                if g[i][0] or p[i][0]:
                    break
                self.assertEqual(ay(p[i][1]), ay(g[i][2]), '%s frame %d' % (cpu, i))
            self.assertEqual(len(p), len(g), cpu + ': both end on the same frame')
        return p

    def test_pattern_longer_than_64_rows(self):
        rows = bytes(0x60 + i % 24 for i in range(100))
        data = song(rows, rows, rows)
        p = self.both(data, 300)
        # 100 rows at speed 1: the end comes on frame 101, not 65
        self.assertEqual((len(p) - 1, p[-1][0]), (101, 2))

    def test_negative_envelope_offset(self):
        # sample 1: one tick, b0 = $20 (envelope offset -16, envelope on),
        # b1 = $8F (envelope slide, amplitude 15); row: envelope $0E with
        # period $0040 and sample 1, then a note
        quiet = bytes([0xD0]) * 9
        data = song(bytes([0x1E, 0x00, 0x40, 0x02, 0x60]) + bytes([0xD0]) * 8, quiet, quiet,
                    sample=bytes([0, 1, 0x20, 0x8F, 0, 0]))
        p = self.both(data, 8)
        self.assertEqual(p[1][1][11] | p[1][1][12] << 8, 0x40 - 16)

    def test_on_off_effect_cuts_the_channel(self):
        # effect 5 (on/off), on 2 ticks, off 1, on channel A's first note
        quiet = bytes([0xD0]) * 21
        data = song(bytes([0x05, 0x60, 2, 1]) + bytes([0xD0]) * 20, quiet, quiet)
        p = self.both(data, 20)
        volumes = [f[1][8] for f in p[1:]]
        self.assertIn(0, volumes)
        self.assertNotEqual(set(volumes), {0})

    def test_amplitude_slide_up_through_zero(self):
        # sample 1, two ticks looping: amplitude 15 sliding down, then 13
        # sliding up -- the slide goes -1 -> 0 on the second tick
        quiet = bytes([0xD0]) * 9
        data = song(bytes([0x60]) + bytes([0xD0]) * 8, quiet, quiet,
                    sample=bytes([0, 2, 0x81, 0x4F, 0, 0, 0xC1, 0x0D, 0, 0]))
        p = self.both(data, 8)
        self.assertEqual([f[1][8] for f in p[1:4]], [14, 13, 14])


if __name__ == '__main__':
    unittest.main()
