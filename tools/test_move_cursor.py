#!/usr/bin/env python3
"""Up and Left at the top of a window load the PREVIOUS window, on both CPUs.

cc65 2.19, the compiler of the 65C02 edition, compiles `target >= count`
(an int against an unsigned char promoted to int) as an unsigned
comparison (`jsr tosicmp0` then `bcc`, where cc65 master branches on the
sign). move_cursor tested that first, so a negative target -- the cursor
less than a page from the top -- passed for one beyond the end, and in any
window but the last Up or Left loaded the next window. The 6502 edition,
built by cc65 master, was right. This runs the real move_cursor and
set_cursor, compiled by each edition's compiler, under sim65.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()
HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))


def section(start, end):
    i = SOURCE.index(start)
    return SOURCE[i:SOURCE.index(end, i)]


C = r'''
#include <stdio.h>
#include <stdlib.h>
#include "src/a2fc_plugin.h"
#define WINDOW (MAX_ENTRIES - 1)
static struct Panel panels[2];
static unsigned char active;
static unsigned int total;            /* active entries of the directory */
static int landed;
#define pan_at(p) (&panels[p])
/* A directory of `total` entries read by windows, as read_panel does. */
static unsigned char read_panel(unsigned char p) {
    struct Panel* pan = pan_at(p);
    unsigned int left = total - pan->first, cap = WINDOW;
    pan->count = (unsigned char)((left > cap ? cap : left) + (pan->first ? 0 : 1));
    pan->more = left > cap;
    return 1;
}
static void show_active(void) {}
static void draw_panel(unsigned char p) { (void)p; }
static void draw_entry(unsigned char p, unsigned char i) { (void)p; (void)i; }
static void draw_info(void) {}
''' + section('static void set_cursor(', '/* Puts the active panel') + r'''
static void land(unsigned char index) { landed = index; set_cursor(pan_at(active), index); }
''' + section('static void move_cursor(int delta)', 'static void swap_panels(void)') + r'''
/* argv: total, first, cursor, delta. Prints first cursor landed. */
int main(int argc, char** argv) {
    struct Panel* pan = pan_at(0);
    (void)argc;
    total = atoi(argv[1]);
    pan->first = atoi(argv[2]);
    read_panel(0);
    pan->cursor = atoi(argv[3]);
    pan->top = 0;
    landed = -1;
    move_cursor(atoi(argv[4]));
    printf("%u %u %d\n", pan->first, pan->cursor, landed);
    return 0;
}
'''

# (total, first, cursor, delta) -> (first, cursor, landed)
CASES = [
    ((400, 139, 12, -18), (0, 139, -1)),       # Left near the top of window 1: back
    ((400, 139, 0, -1), (0, 139, -1)),         # Up at the top of window 1: back
    ((400, 139, 3, -18), (0, 139, -1)),
    ((400, 0, 0, -1), (0, 0, 0)),              # the top of the directory stays
    ((400, 0, 5, -18), (0, 0, 0)),
    ((400, 0, 139, 1), (139, 0, -1)),          # Down at the end of window 0: next
    ((400, 139, 130, 18), (278, 0, -1)),
    ((400, 278, 121, 18), (278, 121, 121)),    # the last window: the last entry
    ((400, 278, 3, -18), (139, 138, -1)),      # back from the last window
    ((400, 139, 60, -18), (139, 42, 42)),      # inside a window
]


def toolchains():
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


class MoveCursor(unittest.TestCase):
    def test_pages_in_the_right_direction(self):
        chains = toolchains()
        if not chains:
            self.skipTest('no cc65 toolchain')
        with tempfile.TemporaryDirectory(prefix='move-cursor-') as d:
            p = Path(d)
            (p / 'move.c').write_text(C)
            for cpu, cl65, sim65, env in chains:
                env = {**os.environ, **env}
                exe = p / f'move-{cpu}'
                subprocess.run([cl65, '-t', cpu, '-O', '-Oirs', '-Cl', '-I', str(ROOT),
                                '-o', str(exe), str(p / 'move.c')], check=True, env=env,
                               capture_output=True)
                for args, expected in CASES:
                    with self.subTest(cpu=cpu, case=args):
                        out = subprocess.check_output([sim65, str(exe), *map(str, args)],
                                                      text=True, env=env, timeout=10)
                        self.assertEqual(tuple(int(w) for w in out.split()), expected)


if __name__ == '__main__':
    unittest.main()
