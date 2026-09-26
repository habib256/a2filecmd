#!/usr/bin/env python3
"""No comparison may depend on which compiler built the edition.

cc65 2.19 (the 65C02 edition) makes `a OP b` unsigned as soon as either
operand is unsigned, an `unsigned char` included; cc65 master (the 6502
edition) follows C, where an unsigned char becomes a signed int. So
`target >= pan->count` with a negative target was false on the 6502 and
true on the 65C02: Up near the top of a directory window loaded the NEXT
window (tools/test_move_cursor.py). 2.19 also computes the difference of two
unsigned chars on eight bits, and divides, shifts and widens to `long` the
expressions it typed unsigned without their sign.

tools/sign_compare.py finds those sites in the syntax tree clang builds of
every unit, with each edition's defines and headers: a comparison unsigned
in either edition with an operand that may be negative, `/`, `%`, `>>` or a
widening of such an operand, an 8-bit difference used on 16 bits. This test

1. refuses any such site in the sources, unless its line, or a comment
   alone on the line above, carries `/* sign-ok: <proof> */` -- and refuses
   an annotation nobody needs;
2. checks the model on shapes compiled by BOTH compilers under sim65: every
   shape the model reports really gives a wrong answer in at least one
   edition, and every shape it accepts gives the right one in both. If a
   compiler upgrade changes the rules, this is where it shows.

A site the analysis reports is fixed in one of three ways: the sign tested
first (move_cursor), the types made to agree (an unsigned variable, a cast
of the side proven non-negative to `unsigned`: cc65 2.19 compiled it so
already, and the 6502 edition's unsigned comparison is the shorter one), or
an annotation with the proof when neither reads well.

    python3 -m unittest tools.test_sign_compare -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import sign_compare  # noqa: E402

HEAD = sign_compare.HEAD

# (expression, the kinds the model reports on its line, the value C
# arithmetic gives -- the programmer's intent) with uc=1, ub=3, si=-2,
# sl=-2, ui=5, sc=-2.
BAD = [
    ('si < uc', {'unsigned-compare'}, 1),               # move_cursor's shape
    ('uc - 2 < ub', {'unsigned-compare'}, 1),
    ('sl < ui', {'unsigned-compare'}, 1),                # long against unsigned int
    ('sc < uc', {'unsigned-compare'}, 1),
    ('si < (uc & 0x7F)', {'unsigned-compare'}, 1),
    ('si < sizeof(int)', {'unsigned-compare'}, 1),       # unsigned in C too: both wrong
    ('(uc - 3) / 2 == -1', {'unsigned-divide'}, 1),
    ('(uc - 3) >> 1 == -1', {'unsigned-divide'}, 1),
    ('(long)(uc - 3) == -2L', {'unsigned-widen'}, 1),
    ('(int)(uc - ub) == -2', {'uchar-difference'}, 1),
    ('ub * 20000 > 0', {'unsigned-compare'}, 1),         # an int overflow, 2.19 unsigned
    ('(int)(ub * 20000) > 0', {'overflow-compare'}, 1),
    ('(unsigned long)(ub << 14) == 49152UL', {'overflow-widen'}, 1),
    ('(unsigned long)(uc | (ub << 14)) == 49153UL', {'unsigned-widen'}, 1),  # ident.c's shape
]
GOOD = [
    ('uc < 5', 1),
    ('uc < ub', 1),
    ('si < (int)uc', 1),
    ('si < 3', 1),
    ('si + 1 < (int)ub', 1),
    ('(uc >> 1) - 2 < 0', 1),
    ('(unsigned char)(uc - ub) == 254', 1),
    ('(unsigned char)(2 + (uc - ub)) == 0', 1),
    ('(int)uc - (int)ub == -2', 1),
    ('(unsigned)(ui - 3) < uc + 2', 1),
    ('(long)si == -2L', 1),
]
ANNOTATED = 'si < uc /* sign-ok: a test of the annotation */'

PRELUDE = r'''
#include <stdio.h>
#include <stdlib.h>
unsigned char uc, ub; int si; long sl; unsigned int ui; signed char sc;
int main(int argc, char** argv)
{
    (void)argc;
    uc = atoi(argv[1]); ub = atoi(argv[2]); si = atoi(argv[3]);
    sl = si; ui = 5; sc = si;
'''


def program():
    """The C file, and the line of each shape in it."""
    lines = PRELUDE.strip('\n').split('\n')
    where = {}
    for expr in [e for e, _, _ in BAD] + [e for e, _ in GOOD] + [ANNOTATED]:
        lines.append('    printf("%%d\\n", (int)(%s' % expr.split(' /*')[0] + '));'
                     + (' /*' + expr.split(' /*')[1] if ' /*' in expr else ''))
        where[expr] = len(lines)
    lines += ['    return 0;', '}', '']
    return '\n'.join(lines), where


def toolchains():
    found = []
    if shutil.which('cl65') and shutil.which('sim65'):
        found.append(('65C02 (cc65 2.19)', shutil.which('cl65'), shutil.which('sim65'),
                      'sim65c02', {}))
    if (HEAD / 'bin/cl65').exists():
        found.append(('6502 (cc65 master)', str(HEAD / 'bin/cl65'), str(HEAD / 'bin/sim65'),
                      'sim6502', {'CC65_HOME': str(HEAD / 'share/cc65')}))
    return found


def analysable():
    return sign_compare.clang() and sign_compare.cc65_include('enh')


class Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not analysable():
            raise unittest.SkipTest('clang or the cc65 headers are missing')
        cls.findings = sign_compare.scan()

    def test_no_site_left(self):
        left = ['%s:%d: %s: %s -- %s' % (f['file'], f['line'], f['kind'], f['text'], f['detail'])
                for f in self.findings if not f['annotated']]
        self.assertEqual(left, [], 'test the sign first, make the types agree, or annotate '
                                   'the line with /* sign-ok: <proof> */ (tools/sign_compare.py)')

    def test_every_annotation_is_needed_and_says_why(self):
        needed = {(f['file'], f['line']) for f in self.findings if f['annotated']}
        stale, empty = [], []
        for path in sorted((ROOT / 'src').rglob('*')):
            if path.suffix not in ('.c', '.h'):
                continue
            rel = str(path.relative_to(ROOT))
            for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                if sign_compare.ANNOTATION not in line:
                    continue
                reason = line.split(sign_compare.ANNOTATION, 1)[1].split('*/')[0].strip()
                if len(reason) < 8:
                    empty.append('%s:%d' % (rel, number))
                if (rel, number) not in needed and (rel, number + 1) not in needed:
                    stale.append('%s:%d' % (rel, number))
        self.assertEqual(empty, [], 'an annotation states its proof')
        self.assertEqual(stale, [], 'an annotation on a line the analysis does not report')


class Model(unittest.TestCase):
    """The analysis against what the two compilers really do."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sign-compare-')
        cls.source, cls.where = program()
        cls.path = Path(cls.tmp.name) / 'shapes.c'
        cls.path.write_text(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_analysis_reports_exactly_the_bad_shapes(self):
        if not analysable():
            self.skipTest('clang or the cc65 headers are missing')
        found = {}
        for f in sign_compare.scan([self.path]):
            found.setdefault(f['line'], set()).add((f['kind'], f['annotated']))
        for expr, kinds, _ in BAD:
            with self.subTest(expr=expr):
                self.assertEqual({k for k, _ in found.get(self.where[expr], set())}, kinds)
        for expr, _ in GOOD:
            with self.subTest(expr=expr):
                self.assertNotIn(self.where[expr], found)
        self.assertEqual(found.get(self.where[ANNOTATED]), {('unsigned-compare', True)})

    def test_the_compilers_answer_as_the_analysis_says(self):
        chains = toolchains()
        if len(chains) < 2:
            self.skipTest('both cc65 toolchains are needed')
        answers = {}
        for name, cl65, sim65, target, env in chains:
            env = {**os.environ, **env}
            exe = Path(self.tmp.name) / target
            subprocess.run([cl65, '-t', target, '-O', '-Oirs', '-Cl', '-o', str(exe),
                            str(self.path)], check=True, env=env, capture_output=True)
            out = subprocess.check_output([sim65, str(exe), '1', '3', '-2'], text=True,
                                          env=env, timeout=10)
            answers[name] = [int(w) for w in out.split()]
        shapes = [(e, v) for e, _, v in BAD] + GOOD
        for i, (expr, intended) in enumerate(shapes):
            got = {name: a[i] for name, a in answers.items()}
            with self.subTest(expr=expr, answers=got):
                if i < len(BAD):
                    self.assertTrue(any(v != intended for v in got.values()),
                                    'a reported shape both editions compute right')
                else:
                    self.assertTrue(all(v == intended for v in got.values()),
                                    'an accepted shape an edition computes wrong')


if __name__ == '__main__':
    unittest.main()
