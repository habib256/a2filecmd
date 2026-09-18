"""The hardware fixtures are the ones the checklist promises.

A session at the machine reads docs/HARDWARE-CHECKLIST.md and compares what
the screen says with what this printed. If the images and the expectations
drift apart, the session proves nothing -- so they are checked here, with
the real images, every time `make test` runs.

    python3 -m unittest tools.test_hw_media -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import hw_media                                                # noqa: E402
import prodos_check                                            # noqa: E402
import mkdos33                                                 # noqa: E402


class HardwareMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='hw-media-test-')
        cls.out = Path(cls.tmp.name)
        sys.argv = ['hw_media.py', '--out', str(cls.out)]
        cls.code = hw_media.main()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_it_writes_what_the_checklist_names(self):
        self.assertEqual(self.code, 0)
        for name in ('HW-CLEAN.po', 'HW-CLEAN.dsk', 'HW-BROKEN.po', 'HW-BROKEN.dsk',
                     'HW-DOS33.dsk', 'EXPECTED.json'):
            self.assertTrue((self.out / name).exists(), name)
        for name in ('HW-CLEAN.dsk', 'HW-BROKEN.dsk', 'HW-DOS33.dsk'):
            self.assertEqual((self.out / name).stat().st_size, 143360, name)

    def test_the_clean_volume_is_clean(self):
        """FIXIT on it must find nothing: a fixture that lies proves nothing."""
        result = prodos_check.check((self.out / 'HW-CLEAN.po').read_bytes())
        self.assertEqual([f.id for f in result.findings], [])
        self.assertTrue(result.complete)

    def test_the_broken_volume_holds_exactly_the_faults_announced(self):
        expected = json.loads((self.out / 'EXPECTED.json').read_text())['HW-BROKEN']
        result = prodos_check.check((self.out / 'HW-BROKEN.po').read_bytes())
        counts = {}
        for f in result.findings:
            counts[f.id] = counts.get(f.id, 0) + 1
        self.assertEqual(counts, expected)
        self.assertEqual(sorted(expected), ['BM_LOST', 'DIR_EOF', 'DIR_PARENT', 'FILE_COUNT'])

    def test_the_dos_disk_holds_its_three_files(self):
        data = (self.out / 'HW-DOS33.dsk').read_bytes()
        self.assertEqual(data[mkdos33.off(17, 0) + 3], 3)          # DOS 3.3 VTOC
        names = []
        track, sector = data[mkdos33.off(17, 0) + 1], data[mkdos33.off(17, 0) + 2]
        while track:
            at = mkdos33.off(track, sector)
            for i in range(7):
                entry = data[at + 11 + i * 35:at + 46 + i * 35]
                if entry[0] and entry[0] != 0xFF:
                    names.append(bytes(b & 0x7F for b in entry[3:33]).rstrip().decode('ascii'))
            track, sector = data[at + 1], data[at + 2]
        self.assertEqual(sorted(names), ['BINARY', 'GREETINGS', 'HELLO'])


if __name__ == '__main__':
    unittest.main()
