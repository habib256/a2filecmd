"""The cc65 code-generation traps, read in every unit that ships.

Each of these cost a release: the compiler produced working-looking code for
correct C, the host harnesses (clang) saw nothing, and only a POM2 bench on
the real overlay showed it. `tools/test_flag_reuse.py` guards the first shape
in `src/a2fc.c`; the resident is one of fifty-five units, and the other
fifty-four are the overlays -- where the writing paths live. So the same two
shapes are read here in all of them, in both editions:

1. a boolean built on the flags of a comparison a branch has already used
   (`jsr booleq` after `bcs`): the DOS-order `.2MG` of 0.8.9;
2. a pointer whose high byte is set and whose low byte is never written
   before an indirect read (`sta ptr1+1 / lda (ptr1),y`, no `sta ptr1` and no
   `stz ptr1`): the page-aligned staging buffer of DUET's validator, which
   read wherever the previous library call had left `ptr1`.

A third trap, `(signed char)f()` losing its sign extension on the 6502
compiler (AWDATA's relative columns), is a source shape: the cast of a call
is refused, the cast of an array element is not, because only the call is
affected.

The fourth known trap, `++` inside a larger expression (paint816.c), has no
mechanical form: every rule that catches `pat[i++ & len]` also catches the
fifty `while (n--)` of the tree, which cc65 compiles correctly. It stays a
review rule -- src/plugins/README.md, "Pitfalls met so far".

Compiling the fifty-five units twice takes about a second: the compiler is
small, and the scan is a read over the assembly it prints.

    python3 -m unittest tools.test_cc65_traps -v
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_flag_reuse import EDITIONS, stale_flag_booleans

# Every C unit the Makefile compiles for the Apple II: the resident and its
# neighbours, the launcher, and one overlay per file.
UNITS = ([ROOT / name for name in ('src/a2fc.c', 'src/format.c', 'src/loader.c',
                                   'src/memory_swap.c')]
         + sorted((ROOT / 'src/plugins').glob('*.c')))

LABEL = re.compile(r'^[A-Za-z_@.][\w@.]*:(.*)$')
LOW = re.compile(r'^\s*(?:sta|stz)\s+(ptr\d|sreg)\s*$')
HIGH = re.compile(r'^\s*sta\s+(ptr\d|sreg)\+1\s*$')
INDIRECT = re.compile(r'^\s*\w+\s+\((ptr\d|sreg)\)(,y)?\s*$')
LEAVES = re.compile(r'^\s*(jsr\s|jmp\s|rts|\.proc|\.endproc)')
SIGNED_CALL = re.compile(r'\(\s*signed\s+char\s*\)\s*[A-Za-z_]\w*\s*\(')


def unset_pointer_low(asm):
    """Indirect reads through a pointer whose low byte this block never wrote.

    A label may be a branch target, and a `jsr` leaves `ptr1` to the library,
    so both start the reasoning again -- which is the trap itself: the value
    read is whatever the previous call happened to leave there.
    """
    found, low, high = [], set(), {}
    for number, raw in enumerate(asm.splitlines(), 1):
        label = LABEL.match(raw)
        if label:                              # a branch may arrive here
            low, high, line = set(), {}, label[1]
        else:
            line = raw
        if not line.strip() or line.lstrip().startswith(';'):
            continue
        match = LOW.match(line)
        if match:
            low.add(match[1])
            continue
        match = HIGH.match(line)
        if match:
            high[match[1]] = number
            continue
        match = INDIRECT.match(line)
        if match and match[1] in high and match[1] not in low:
            found.append('%d: %s, %s+1 set at line %d and %s never'
                         % (number, line.strip(), match[1], high[match[1]], match[1]))
            continue
        if LEAVES.match(line):
            low, high = set(), {}
    return found


def compile_unit(unit, compiler, env, target, defines, out):
    """The Makefile's own plugin recipe: same flags, same defines."""
    cmd = [compiler, '-t', target, *defines, '-D', 'A2FC_VERSION="test"',
           '-O', '-Oirs', '-Cl', '--codesize', '100', '-I', str(ROOT / 'src'),
           '-o', str(out), str(unit)]
    result = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **env})
    return result.returncode, result.stderr


class Codegen(unittest.TestCase):
    def test_every_unit_in_both_editions(self):
        ran = 0
        for name, compiler, env, target, defines in EDITIONS:
            if not (compiler == 'cc65' or Path(compiler).exists()):
                continue
            ran += 1
            with self.subTest(edition=name), tempfile.TemporaryDirectory() as tmp:
                def work(unit):
                    out = Path(tmp) / (unit.stem + '.s')
                    code, err = compile_unit(unit, compiler, env, target, defines, out)
                    return unit, code, err, out
                with ThreadPoolExecutor(max_workers=8) as pool:
                    built = list(pool.map(work, UNITS))
                complaints = []
                for unit, code, err, out in built:
                    if code:
                        complaints.append('%s did not compile: %s' % (unit.name, err.strip()[:200]))
                        continue
                    asm = out.read_text()
                    for line in stale_flag_booleans(asm):
                        complaints.append('%s: boolean on stale flags, %s' % (unit.name, line))
                    for line in unset_pointer_low(asm):
                        complaints.append('%s: pointer low byte never written, %s' % (unit.name, line))
                self.assertEqual(complaints, [], '%s: %d units read' % (name, len(built)))
        if not ran:
            self.skipTest('no cc65 toolchain')

    def test_no_signed_cast_of_a_call(self):
        """cc65 master drops the sign extension: extend a byte result by hand."""
        found = []
        for path in sorted((ROOT / 'src').rglob('*')):
            if path.suffix not in ('.c', '.h'):
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if SIGNED_CALL.search(re.sub(r'//.*', '', line)):
                    found.append('%s:%d: %s' % (path.relative_to(ROOT), number, line.strip()))
        self.assertEqual(found, [], 'write `v = f(); if (v > 127) v -= 256;` instead')

    def test_the_pointer_check_sees_the_shape(self):
        """DUET's validator, as cc65 wrote it, and as it must be written."""
        bad = ('\tlda     #$24\n\tclc\n\tadc     _p+1\n\tsta     ptr1+1\n'
               '\tldy     _p\n\tlda     (ptr1),y\n')
        fixed = ('\tstz     ptr1\n\tlda     #$24\n\tclc\n\tadc     _p+1\n\tsta     ptr1+1\n'
                 '\tldy     _p\n\tlda     (ptr1),y\n')
        stored = ('L0004:\tsta     ptr1\n\ttxa\n\tadc     #$24\n\tsta     ptr1+1\n'
                  '\tldy     #$00\n\tlda     (ptr1),y\n')
        self.assertEqual(len(unset_pointer_low(bad)), 1)
        self.assertEqual(unset_pointer_low(fixed), [])
        self.assertEqual(unset_pointer_low(stored), [])   # the low store shares the label's line

    def test_the_call_shape_is_what_is_refused(self):
        self.assertTrue(SIGNED_CALL.search('int dc = (signed char)cget();'))
        self.assertFalse(SIGNED_CALL.search('int dc = (signed char)bytes[1];'))


if __name__ == '__main__':
    unittest.main()
