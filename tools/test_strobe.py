"""The keyboard strobe is acknowledged by a write, never by a discarded read.

`(void)*(volatile unsigned char*)0xC010;` reads nothing: cc65 drops a read
whose value is thrown away, volatile or not, so the key stayed in $C000. An
Escape that cancelled a scan in FIXIT, REPAIR, VOLINFO, VERIFY, TXTCONV, the
util.h overlays or SEARCH was then read again by the next cgetc -- FIXIT
closed its findings screen at once. Writing $C010 clears the strobe as well
(pt3.c, duet.c and music.c always did).
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCARDED = re.compile(r'\(void\)\s*\*\s*\(\s*(volatile\s+)?unsigned\s+char\s*\*\s*\)\s*0x[cC]010')


class Strobe(unittest.TestCase):
    def test_no_discarded_strobe_read_in_c(self):
        found = []
        for path in sorted((ROOT / 'src').rglob('*')):
            if path.suffix in ('.c', '.h'):
                for n, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                    if DISCARDED.search(line):
                        found.append('%s:%d' % (path.relative_to(ROOT), n))
        self.assertEqual(found, [])

    def test_cc65_emits_the_strobe_write(self):
        """The form used instead does reach the code, and the old one does not."""
        src = ('void f(void) { if (*(volatile unsigned char*)0xC000 == 155) '
               '{ %s } }\n')
        with tempfile.TemporaryDirectory() as tmp:
            out = {}
            for name, stmt in (('write', '*(volatile unsigned char*)0xC010 = 0;'),
                               ('read', '(void)*(volatile unsigned char*)0xC010;')):
                c = Path(tmp) / (name + '.c')
                c.write_text(src % stmt)
                s = Path(tmp) / (name + '.s')
                subprocess.run(['cc65', '-t', 'apple2enh', '-O', '-Oirs', '-Cl',
                                '-o', str(s), str(c)], check=True, capture_output=True)
                out[name] = '$C010' in s.read_text()
        self.assertTrue(out['write'], 'the write must be emitted')
        self.assertFalse(out['read'], 'if cc65 ever emits the read, this note is stale')


if __name__ == '__main__':
    sys.exit(unittest.main())
