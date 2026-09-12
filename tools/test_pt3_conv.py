"""PT3 1.77MHz -> 1MHz period conversion: the real 6502 routine, every input.

The PT3 library converts every period it writes to the AY (tones A/B/C and
the envelope) by 9/16, because PT3 modules are written for a 1.77MHz AY and
the Mockingboard's runs at 1.023MHz. The inline copies it had TRUNCATED the
result, which a 12-bit tone period hides but a small envelope period does
not: a buzz bass tunes the envelope to its note through periods as small as
37, and 37 -> 20 (not 20.8) put it 69 cents sharp of its own note. The
envelope copy also lost P*8's top bits for P >= 8192 and masked the result
with a tone's AND #$0F.

This assembles `conv916` straight out of src/plugins/pt3lib/core.inc and
runs it under sim65 on all 65536 16-bit periods, through the envelope's
register pair and a tone's: the result must be round(9P/16), exactly.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'src' / 'plugins' / 'pt3lib' / 'core.inc'


def routine():
    text = CORE.read_text()
    m = re.search(r'^conv916:\n(.*?)^\trts\b[^\n]*\n', text, re.S | re.M)
    if not m:
        raise AssertionError('conv916 not found in core.inc')
    return 'conv916:\n' + m.group(1) + '\trts\n'


HARNESS_S = '''
AY_REGISTERS = $70
.export _conv_env, _conv_tone
.code
; unsigned __fastcall__ conv_env(unsigned p): through R11/R12
_conv_env:
\tsta\tAY_REGISTERS+11
\tstx\tAY_REGISTERS+12
\tldx\t#11
\tjsr\tconv916
\tlda\tAY_REGISTERS+11
\tldx\tAY_REGISTERS+12
\trts
; unsigned __fastcall__ conv_tone(unsigned p): through R4/R5, X kept
_conv_tone:
\tsta\tAY_REGISTERS+4
\tstx\tAY_REGISTERS+5
\tldx\t#4
\tjsr\tconv916
\tcpx\t#4
\tbne\tclobbered
\tlda\tAY_REGISTERS+4
\tldx\tAY_REGISTERS+5
\trts
clobbered:
\tlda\t#$ff
\ttax
\trts
'''

HARNESS_C = r'''
#include <stdio.h>
unsigned __fastcall__ conv_env(unsigned p);
unsigned __fastcall__ conv_tone(unsigned p);
int main(void)
{
    unsigned long p;
    for (p = 0; p < 65536UL; ++p) {
        unsigned want = (unsigned)((9UL * p + 8UL) >> 4);
        unsigned got = conv_env((unsigned)p);
        if (got != want) { printf("env %lu: %u, want %u\n", p, got, want); return 1; }
        if (p < 4096UL) {
            got = conv_tone((unsigned)p);
            if (got != want) { printf("tone %lu: %u, want %u\n", p, got, want); return 2; }
        }
    }
    puts("ok");
    return 0;
}
'''


@unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'), 'needs cl65 and sim65')
class Conv916(unittest.TestCase):
    def test_every_period_rounds_exactly(self):
        with tempfile.TemporaryDirectory(prefix='pt3-conv-') as tmp:
            t = Path(tmp)
            (t / 'conv.s').write_text(HARNESS_S + routine())
            (t / 'main.c').write_text(HARNESS_C)
            subprocess.run(['cl65', '-t', 'sim6502', '-O', '-o', str(t / 'prog'),
                            str(t / 'main.c'), str(t / 'conv.s')],
                           check=True, capture_output=True)
            r = subprocess.run(['sim65', str(t / 'prog')], capture_output=True,
                               text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('ok', r.stdout)

    def test_buzz_bass_stays_near_its_note(self):
        # The envelope periods AuTumn'99 tunes its buzz bass with: the
        # rounded conversion keeps each within 27 cents of its unison note
        # (the truncated one reached 69). Pure arithmetic, no 6502.
        import math
        worst = 0.0
        for ep in (37, 42, 45, 50, 56, 63, 67, 75, 84, 85, 90, 100, 126, 224, 240):
            env = (9 * ep + 8) >> 4
            tone = (9 * 16 * ep + 8) >> 4
            worst = max(worst, abs(1200 * math.log2(tone / (16 * env))))
        self.assertLessEqual(worst, 27.5)


if __name__ == '__main__':
    unittest.main()
