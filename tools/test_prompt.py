#!/usr/bin/env python3
"""The row-22 input (prompt) accepts exactly what it always did, on both CPUs.

prompt() types every name A2FC writes to disk -- R rename, K mkdir, the
volume name, the ERASE of a wipe -- and the hexadecimal fields. It was
rewritten for room in the language card (the index of a deleted or added
character as a statement of its own instead of `input[--len]` and
`input[len++]`, which cc65 computed through ptr1). This runs the real
function, compiled by each edition's compiler, under sim65, and compares
every key in every state with a model of the rules: letters (lowercase
folded), then also digits and '.' for a name, 15 at most; 0-9 A-F for a hex
field of exactly `hex` digits; Left and Delete erase; Escape returns 0 with
the text left as typed; Return accepts a non-empty name or a full hex field.
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
#include <string.h>
#include <stdlib.h>
#include "src/a2fc_plugin.h"
char input[NAME_LEN];
static const unsigned char* keys;
static unsigned char cleared, guard;
/* The keyboard latch: a key waiting in $C000 until the strobe is stored.
 * In a burst, each key arrives while the previous one is being handled --
 * during the redraw of the row (two keys back to back). */
static unsigned char latch, burst, strobes;
static void question_begin(void) { latch = 0; ++strobes; }
static void open_row22(void) {}
static void cputs_(const char* s) { (void)s; }
#define cputs cputs_
static void cputc_(char c) { (void)c; }
#define cputc cputc_
static unsigned char revers_(unsigned char on) { (void)on; return 0; }
#define revers revers_
/* The scripted keys; Return once they run out, so that no case loops. */
static char cgetc_(void) {
    char k;
    if (latch) { k = (char)latch; latch = 0; }
    else k = *keys ? (char)*keys++ : KEY_RETURN;
    if (burst && *keys) latch = *keys++;
    return k;
}
#define cgetc cgetc_
static void clear_row(unsigned char row) { if (row == 22) ++cleared; }
''' + section('static unsigned char prompt(const char* label', 'unsigned int __fastcall__ hex_value') + r'''
/* One case: hex, initial text ("-" for none), then the keys as decimal
 * numbers. Prints the verdict, whether row 22 was cleared, and the text. */
static unsigned char script[64];
static void run(unsigned char hex, const char* initial, unsigned char n) {
    unsigned char r;
    script[n] = 0;
    keys = script;
    cleared = 0;
    guard = 0xA5;
    strobes = 0;
    if (burst) latch = 'Q';     /* typed before the question: dropped */
    r = prompt("L", initial, hex);
    printf("%u %u %s|%u\n", r, cleared + strobes - 1, input, guard);
}
/* argv: hex initial key... ; "all" as the first argument runs the sweep:
 * for each mode and starting text, every key 1-255 then Return. */
int main(int argc, char** argv) {
    static const unsigned char modes[] = { 0, 2, 4 };
    static const char* const starts[] = { 0, "A", "AB", "ABCDEFGHIJKLMNO", "1F", "C0DE" };
    unsigned char m, s, k;
    if (argc > 1 && !strcmp(argv[1], "burst")) { burst = 1; --argc; ++argv; }
    if (argc > 1 && !strcmp(argv[1], "all")) {
        for (m = 0; m < 3; ++m)
            for (s = 0; s < 6; ++s)
                for (k = 1; k; ++k) {
                    if (k == KEY_RETURN) continue;
                    script[0] = k; script[1] = KEY_RETURN;
                    run(modes[m], starts[s], 2);
                }
        return 0;
    }
    for (k = 0; k + 3 < argc && k < 63; ++k) script[k] = (unsigned char)atoi(argv[k + 3]);
    run((unsigned char)atoi(argv[1]), strcmp(argv[2], "-") ? argv[2] : 0, k);
    return 0;
}
'''


def model(hex_, initial, keys):
    """The rules of prompt(): (verdict, cleared, text)."""
    text = list(initial or '')
    most = hex_ or 15
    for k in keys + [13]:
        if k == 27:
            return 0, 1, ''.join(text)
        if k == 13:
            return (int(len(text) == most) if hex_ else int(len(text) != 0)), 1, ''.join(text)
        if k in (8, 127):
            if text:
                text.pop()
            continue
        if ord('a') <= k <= ord('z'):
            k -= 32
        if len(text) >= most:
            continue
        c = chr(k)
        digit = '0' <= c <= '9'
        if hex_:
            ok = digit or 'A' <= c <= 'F'
        else:
            ok = 'A' <= c <= 'Z' or (len(text) and (digit or c == '.'))
        if ok:
            text.append(c)
    raise AssertionError('unreachable')


def expected_line(hex_, initial, keys):
    r, cleared, text = model(hex_, initial, keys)
    return '%u %u %s|%u' % (r, cleared, text, 0xA5)


SCRIPTS = [
    (0, None, [ord(c) for c in 'newdir']),            # folded to NEWDIR
    (0, None, [ord(c) for c in '1abc']),              # a leading digit refused
    (0, None, [ord(c) for c in '.x']),                # a leading period refused
    (0, None, [ord(c) for c in 'a.1']),               # then both accepted
    (0, None, [ord('A')] * 20),                       # 15 at most
    (0, 'OLDNAME', [8, 8, 8, ord('x')]),              # Left erases
    (0, 'OLD', [127, 127, 127, 127, 127]),            # Delete past the start
    (0, 'OLD', [8, 8, 8]),                            # erased to nothing: Return refuses
    (0, 'KEEP', [ord('z'), 27]),                      # Escape: 0, text as typed
    (0, None, [27]),
    (2, None, [ord('f')]),                            # one digit of two: refused
    (2, None, [ord('f'), ord('0')]),                  # F0 accepted
    (2, None, [ord('g'), ord('1'), ord('2'), ord('3')]),
    (4, '1F', [ord('a'), ord('b'), ord('c')]),
    (4, None, [ord('.'), ord('9'), 8, ord('9'), ord('9'), ord('9'), ord('9')]),
    (0, None, [0xC1, 0xE1, ord('A')]),                # high-bit keys refused
]


BURSTS = [
    (0, None, [ord(c) for c in 'ERASE']),
    (0, None, [ord(c) for c in 'FIX']),
    (0, None, [ord(c) for c in 'free']),
    (0, None, [ord(c) for c in 'longname.1']),
    (4, None, [ord(c) for c in 'c0de']),
]


def toolchains():
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('sim65c02', shutil.which('cl65'), shutil.which('sim65'), {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('sim6502', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


class Prompt(unittest.TestCase):
    def test_every_key_in_every_state(self):
        chains = toolchains()
        if not chains:
            self.skipTest('no cc65 toolchain')
        modes, starts = (0, 2, 4), (None, 'A', 'AB', 'ABCDEFGHIJKLMNO', '1F', 'C0DE')
        sweep = [expected_line(m, s, [k]) for m in modes for s in starts
                 for k in range(1, 256) if k != 13]
        with tempfile.TemporaryDirectory(prefix='prompt-') as d:
            p = Path(d)
            (p / 'prompt.c').write_text(C)
            for cpu, cl65, sim65, env in chains:
                env = {**os.environ, **env}
                exe = p / f'prompt-{cpu}'
                subprocess.run([cl65, '-t', cpu, '-O', '-Oirs', '-Cl', '--codesize', '100',
                                '-I', str(ROOT), '-o', str(exe), str(p / 'prompt.c')],
                               check=True, env=env, capture_output=True)
                with self.subTest(cpu=cpu, case='sweep'):
                    out = subprocess.check_output([sim65, str(exe), 'all'], text=True,
                                                  env=env, timeout=120)
                    got = out.splitlines()
                    self.assertEqual(len(got), len(sweep))
                    bad = [(i, g, e) for i, (g, e) in enumerate(zip(got, sweep)) if g != e]
                    self.assertEqual(bad[:5], [])
                for hex_, initial, keys in SCRIPTS:
                    with self.subTest(cpu=cpu, case=(hex_, initial, keys)):
                        out = subprocess.check_output(
                            [sim65, str(exe), str(hex_), initial or '-', *map(str, keys)],
                            text=True, env=env, timeout=10)
                        self.assertEqual(out.strip(), expected_line(hex_, initial, keys))
                # Bug hunt 3: two keys back to back. The strobe was cleared
                # at each redraw of the row and erased the key typed during
                # it: once before the first key now, never inside the loop.
                for hex_, initial, keys in SCRIPTS + BURSTS:
                    with self.subTest(cpu=cpu, case=('burst', hex_, initial, keys)):
                        out = subprocess.check_output(
                            [sim65, str(exe), 'burst', str(hex_), initial or '-', *map(str, keys)],
                            text=True, env=env, timeout=10)
                        self.assertEqual(out.strip(), expected_line(hex_, initial, keys))


if __name__ == '__main__':
    unittest.main()
