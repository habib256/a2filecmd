"""FANTA.SYSTEM's wait at the original speed lasts fv_wait cycles.

waitorig (src/fanta/fanta.s) counts units of 257 cycles from bytes 1 and 2
of the 32-bit fv_wait. It used to clip the wait whenever byte 2 was set as
well as byte 3: every frame that the original player takes 65,536 cycles
or more longer to draw -- large solids reach 240,000 -- then froze for 16
million cycles, about 16 seconds, with no key read. The routine is taken
from fanta.s as it stands and run under sim65 on both processors; the
cycles counted must follow fv_wait, and only a wait past 16 million is
clipped.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
        .export _run, _fv_wait
        .bss
_fv_wait:
fv_wait: .res 4
wl:     .res 2
        .code
_run:   jmp     waitorig
%s
'''

MAIN = r'''
extern unsigned long fv_wait;
void run(void);
int main(int argc, char** argv)
{
    /* eight hex digits, parsed at a cost that does not depend on them */
    unsigned char i, c;
    unsigned long v = 0;
    (void)argc;
    for (i = 0; i < 8; ++i) {
        c = argv[1][i];
        v = (v << 4) | (c <= '9' ? c - '0' : c - 'a' + 10);
    }
    fv_wait = v;
    run();
    return 0;
}
'''


def waitorig():
    text = (ROOT / 'src/fanta/fanta.s').read_text()
    m = re.search(r'^waitorig:.*?^@done:\s+rts\n', text, re.M | re.S)
    assert m, 'waitorig not found in fanta.s'
    return m.group(0)


class FantaWait(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        work = Path(cls.tmp.name)
        (work / 'wait.s').write_text(HARNESS % waitorig())
        (work / 'main.c').write_text('#include <stdlib.h>\n' + MAIN)
        cls.exe = {}
        for cpu, target in (('6502', 'sim6502'), ('65c02', 'sim65c02')):
            exe = work / ('wait-' + cpu)
            subprocess.run(['cl65', '-t', target, '-O', '-o', str(exe),
                            str(work / 'main.c'), str(work / 'wait.s')],
                           check=True, capture_output=True, cwd=work)
            cls.exe[cpu] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cycles(self, cpu, wait, limit=40_000_000):
        p = subprocess.run(['sim65', '-c', '-x', str(limit), str(self.exe[cpu]), '%08x' % wait],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, 'wait $%X on %s: %s' % (wait, cpu, p.stderr + p.stdout))
        m = re.search(r'(\d+)\s+cycles', p.stdout + p.stderr)
        self.assertIsNotNone(m, p.stdout + p.stderr)
        return int(m.group(1))

    def test_wait_follows_fv_wait(self):
        for cpu in self.exe:
            base = self.cycles(cpu, 0)
            for wait in (0x100, 0xFF00, 0x10000, 0x12000, 0x3A980, 0xFFFFFF):
                spent = self.cycles(cpu, wait) - base
                # units of 257 cycles from bits 8-23 (the bits below are left);
                # the loop runs about 2% over its nominal unit
                want = (wait >> 8) * 257
                self.assertLess(abs(spent - want), 64 + want * 3 // 100,
                                '%s: fv_wait $%X took %d cycles, not %d' % (cpu, wait, spent, want))

    def test_only_past_16_million_is_clipped(self):
        for cpu in self.exe:
            base = self.cycles(cpu, 0)
            spent = self.cycles(cpu, 0x1000000) - base
            want = 0xFFFF * 257
            self.assertLess(abs(spent - want), 64 + want * 3 // 100, cpu)


if __name__ == '__main__':
    unittest.main()
