"""VERIFY volume-list unit: DOS 3.3 rows must not READ_BLOCK device $00."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/plugins/verify.c').read_text()


def section(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end, SOURCE.index(start))]


HARNESS = r'''
#define __fastcall__
#include <string.h>
#include "src/a2fc_plugin.h"
static const struct Entry* e;
''' + section('static unsigned char volume_unit(void)',
              '/* Volume entries carry the driver unit') + r'''
int main(void)
{
    struct Entry dos, prodos, nameless;
    memset(&dos, 0, sizeof dos);
    strcpy(dos.name, "DOS 3.3");
    dos.access = 0;
    dos.mdate = 0x60;                 /* unshifted unit, as read_volumes stores it */
    e = &dos;
    if (volume_unit()) return 1;      /* must refuse, not shift to $00 */
    if ((unsigned char)(dos.mdate << 4) != 0) return 2;  /* the old mapping */

    memset(&prodos, 0, sizeof prodos);
    strcpy(prodos.name, "/WORKHD");
    prodos.access = 0xC3;
    prodos.mdate = 6;                 /* DSSS >> 4 */
    e = &prodos;
    if (volume_unit() != 0x60) return 3;

    memset(&nameless, 0, sizeof nameless);
    nameless.access = 0xC3;
    nameless.mdate = 6;
    e = &nameless;
    if (volume_unit()) return 4;      /* no leading slash: not a volume */

    prodos.access = 0;
    e = &prodos;
    if (volume_unit()) return 5;      /* locked-out the same way as DOS 3.3 */
    return 0;
}
'''


class VerifyVolume(unittest.TestCase):
    def test_volume_unit_refuses_dos33_rows(self):
        with tempfile.TemporaryDirectory(prefix='verify-vol-') as d:
            p = Path(d)
            (p / 'test.c').write_text(HARNESS)
            subprocess.run(['cc', '-std=c99', '-fsanitize=address,undefined',
                            '-I', str(ROOT), str(p / 'test.c'), '-o', str(p / 'test')],
                           check=True, capture_output=True)
            self.assertEqual(subprocess.run([str(p / 'test')]).returncode, 0)

    def test_verify_volume_uses_the_guard_before_any_block(self):
        body = section('static void verify_volume(void)', 'void plugin_entry(void)')
        self.assertIn('volume_unit()', body)
        self.assertIn('if (!bp.unit)', body)
        self.assertLess(body.index('volume_unit()'), body.index('for (bp.block'))
        self.assertIn('if (!any && did)', SOURCE)


if __name__ == '__main__':
    unittest.main()
