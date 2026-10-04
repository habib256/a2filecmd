"""PT3 period conversion to the Mockingboard's clock: the real 6502 routine, every input.

PT3 modules are written for the ZX Spectrum 128's AY at 1.7734 MHz; the
Mockingboard's AY runs on the Apple II clock, 1.0227 MHz. pt3_lib converts
every period it writes (tones A/B/C, envelope, noise) with `conv_mb`:
round(P x 1181 / 2048), 1181/2048 = 0.576660 for 1.0227/1.7734 =
0.576689 (0.09 cent). The routine it replaced (2026-10-03) used 9/16, which
played every module 43 cents sharp; before that, truncating inline copies
put buzz basses up to 69 cents off their own note.

This assembles `conv_mb` straight out of src/plugins/pt3lib/core.inc and
runs it under sim65 on all 65536 16-bit periods, through the envelope's
register pair and a tone's: the result must be (1181 P + 1024) >> 11
exactly, and for every tone period within 0.62 of the exact clock ratio.
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
    m = re.search(r'^(conv_mb:\n.*?^conv_add:\n.*?^\trts\b)[^\n]*\n', text, re.S | re.M)
    if not m:
        raise AssertionError('conv_mb/conv_add not found in core.inc')
    return m.group(1) + '\n'


HARNESS_S = '''
AY_REGISTERS = $70
.export _conv_env, _conv_tone
.code
; unsigned __fastcall__ conv_env(unsigned p): through R11/R12
_conv_env:
\tsta\tAY_REGISTERS+11
\tstx\tAY_REGISTERS+12
\tldx\t#11
\tjsr\tconv_mb
\tlda\tAY_REGISTERS+11
\tldx\tAY_REGISTERS+12
\trts
; unsigned __fastcall__ conv_tone(unsigned p): through R4/R5, X kept
_conv_tone:
\tsta\tAY_REGISTERS+4
\tstx\tAY_REGISTERS+5
\tldx\t#4
\tjsr\tconv_mb
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
        unsigned want = (unsigned)((1181UL * p + 1024UL) >> 11);
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
class ConvMb(unittest.TestCase):
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

    def test_formula_is_the_clock_ratio(self):
        # Pure arithmetic: every tone period within 0.62 of P x 1.0227/1.7734
        # (rounding plus the 11-bit multiplier), and AuTumn'99's buzz-bass
        # envelope periods within 27 cents of their unison tone (rounding a
        # 20-unit period cannot do better).
        import math
        k = 1.0227 / 1.7734
        for p in range(4096):
            self.assertLessEqual(abs(((1181 * p + 1024) >> 11) - p * k), 0.62, p)
        worst = 0.0
        for ep in (37, 42, 45, 50, 56, 63, 67, 75, 84, 85, 90, 100, 126, 224, 240):
            env = (1181 * ep + 1024) >> 11
            tone = (1181 * 16 * ep + 1024) >> 11
            worst = max(worst, abs(1200 * math.log2(tone / (16 * env))))
        self.assertLessEqual(worst, 27)   # 37 -> 21: half a unit of rounding is up to 41 cents there

if __name__ == '__main__':
    unittest.main()
