"""cc65 must not build a boolean out of another comparison's flags.

`img_dsk = copy_buf[0x0C] == 0;`, written after `if (copy_buf[0x0C] > 1)`,
compiled to `cmp #$02 / bcs bad / jsr booleq`: the second test reused the
flags of the first, so the value was "equal to 2", always false, and every
DOS-order `.2MG` image was read as ProDOS (bench/dosimage.py caught it).

The compiler is what it is, so the shape is what we refuse: a `jsr boolXX`
whose flags come from a comparison a branch has already consumed. This
compiles the resident with the real flags of each edition and reads the
assembly. A toolchain that is not installed is skipped, not ignored.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOL = re.compile(r'^\s*jsr\s+bool\w+')
BRANCH = re.compile(r'^\s*(b(cc|cs|eq|ne|mi|pl|vc|vs)|j(cc|cs|eq|ne|mi|pl))\s')
INSTRUCTION = re.compile(r'^\s+\S')

HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
# (name, compiler, environment, target, defines): the two editions of the Makefile.
EDITIONS = [
    ('65C02', 'cc65', {}, 'apple2enh', ['-DA2FC_BIG_BINARY2']),
    ('6502', str(HEAD / 'bin/cc65'), {'CC65_HOME': str(HEAD / 'share/cc65')}, 'apple2',
     ['-DA2FC_6502', '-DA2FC_NOMOUSE', '-DA2FC_BIG_BINARY2']),
]


def stale_flag_booleans(asm):
    """The lines where a boolean is made from flags a branch already used."""
    found, previous = [], None
    for number, line in enumerate(asm.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(';') or stripped.startswith('.'):
            continue
        if BOOL.match(line) and previous is not None and BRANCH.match(previous):
            found.append('%d: %s after %s' % (number, stripped, previous.strip()))
        if INSTRUCTION.match(line):
            previous = line
        elif ':' in line:                      # a label, alone or with an instruction
            body = line.split(':', 1)[1]
            previous = line if body.strip() else None
    return found


class FlagReuse(unittest.TestCase):
    def test_resident(self):
        ran = 0
        for name, compiler, env, target, defines in EDITIONS:
            if not (compiler == 'cc65' or Path(compiler).exists()):
                continue
            with self.subTest(edition=name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / 'a2fc.s'
                cmd = [compiler, '-t', target, *defines, '-D', 'A2FC_VERSION="test"',
                       '-O', '-Oirs', '-Cl', '--codesize', '100', '-I', str(ROOT / 'src'),
                       '-o', str(out), str(ROOT / 'src/a2fc.c')]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        env={**os.environ, **env})
                if result.returncode:
                    self.skipTest('%s: %s' % (name, result.stderr.strip()[:200]))
                ran += 1
                self.assertEqual(stale_flag_booleans(out.read_text()), [], name)
        if not ran:
            self.skipTest('no cc65 toolchain')

    def test_the_check_sees_the_shape(self):
        bad = '\tlda\t_copy_buf+12\n\tcmp\t#$02\n\tbcs\tL1\n\tjsr\tbooleq\n\tsta\t_img_dsk\n'
        good = '\tlda\t_copy_buf+12\n\tcmp\t#$02\n\tbcs\tL1\n\tlda\t_order\n\tjsr\tbooleq\n'
        self.assertEqual(len(stale_flag_booleans(bad)), 1)
        self.assertEqual(stale_flag_booleans(good), [])


if __name__ == '__main__':
    unittest.main()
