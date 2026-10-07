#!/usr/bin/env python3
"""IMGPUT's walk of the image, as each edition's compiler builds it.

IMGPUT (src/plugins/imgput.c) walks every directory and index block of the
image before it writes (prodos_claims.h), with a budget of one read per
block of the volume so that a looping chain ends. The budget is spent by
`--claims_budget` inside an `&&`: cc65 2.19 (the 65C02 edition's compiler)
tests that 16-bit decrement on its LOW byte when it does not borrow, so the
budget "ran out" at 256 -- after 23 reads of a 140K image -- and IMGPUT
refused a sound image with ~22 files as "Image damaged: nothing written.
Run FIXIT." (third bug hunt; tools/test_cc65_traps.py names the shape).

This runs the real prodos_claims.h and imgput.c's own claims_read (taken
from the source, so the test follows a rewrite) over a generated 280-block
volume: a root directory of two blocks and N sapling files, under sim65
with each compiler. The walk must call the image sound, whatever N.

    python3 -m unittest tools.test_imgput_walk -v
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char dirb[512], idx[512];
static unsigned int vol_blocks = 280, dir_first = 2, dir_blk = 3, nfiles, reads;
static unsigned char src;

static unsigned int rd16(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }
static void spin(void) { }
static unsigned char stop(void) { return 0; }
static unsigned char marked_used(unsigned int b) { return b < vol_blocks; }
static unsigned char claims_used(unsigned int b) { return b > 1 && marked_used(b); }

/* Blocks 2 and 3: the root directory, the volume header first, then N
 * sapling entries; blocks 10...: their index blocks, one data block each. */
static unsigned char image_read(unsigned int b, unsigned char* to)
{
    unsigned char k, i;
    unsigned char* e;
    ++reads;
    memset(to, 0, 512);
    if (b == 2 || b == 3) {
        to[2] = b == 2 ? 3 : 0;
        to[0] = b == 3 ? 2 : 0;
        for (k = 0; k < 13; ++k) {
            e = to + 4 + k * 0x27;
            if (b == 2 && k == 0) {
                e[0] = 0xF4; memcpy(e + 1, "TEST", 4);
                to[0x23] = 0x27; to[0x24] = 13;
                continue;
            }
            i = b == 2 ? k - 1 : 12 + k;
            if (i >= nfiles) continue;
            e[0] = 0x21; e[1] = 'F';
            e[0x11] = 10 + i;
        }
    } else if (b >= 10 && b < 10 + 25) {
        to[0] = 200;
    }
    return 1;
}
#define source_read(s, b, to) image_read(b, to)

%(claims_read)s

#define CLAIMS_FILE(b) ((b)!=dir_first && (b)!=dir_blk)
#define CLAIMS_DIR dirb
#define CLAIMS_IDX idx
#define CLAIMS_WORD rd16
#define CLAIMS_BLOCKS vol_blocks
#define CLAIMS_TARGET dir_first
#include "prodos_claims.h"

int main(int argc, char** argv)
{
    unsigned char r;
    nfiles = (unsigned)atoi(argv[1]);
    r = claims_walk();
    printf("%%u %%u %%u\n", r, reads, claims_met);
    return 0;
}
'''


def claims_read_source():
    """imgput.c's budget and claims_read, as they are written there."""
    text = (ROOT / 'src/plugins/imgput.c').read_text()
    match = re.search(r'^static unsigned int claims_budget;\n'
                      r'static unsigned char claims_read\(.*?\n\}\n', text, re.S | re.M)
    if not match:
        raise AssertionError('claims_read not found in imgput.c')
    return match[0]


def toolchains():
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


class ImgputWalk(unittest.TestCase):
    def test_a_sound_image_is_sound_in_both_editions(self):
        chains = toolchains()
        if not chains:
            self.skipTest('no cc65 toolchain')
        with tempfile.TemporaryDirectory(prefix='imgput-walk-') as d:
            c = Path(d) / 'walk.c'
            c.write_text(HARNESS % {'claims_read': claims_read_source()})
            for cpu, cl65, sim65, env in chains:
                env = {**os.environ, **env}
                exe = Path(d) / ('walk-' + cpu)
                subprocess.run([cl65, '-t', cpu, '-O', '-Oirs', '-Cl', '--codesize', '100',
                                '-I', str(ROOT / 'src/plugins'), '-o', str(exe), str(c)],
                               check=True, env=env, capture_output=True)
                for files in (5, 21, 22, 25):
                    with self.subTest(cpu=cpu, files=files):
                        out = subprocess.check_output([sim65, str(exe), str(files)],
                                                      text=True, env=env, timeout=20).split()
                        # sound, every block read once (2 directory + N index), panel met
                        self.assertEqual(out, ['1', str(2 + files), '1'],
                                         '%s, %d files: %s' % (cpu, files, out))


if __name__ == '__main__':
    unittest.main()
