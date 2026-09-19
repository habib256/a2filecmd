"""The launcher's machine check, src/machine_check.inc, run under sim65.

The 65C02 edition checked the firmware ($FBC0) and took the processor on
trust: an enhanced IIe with a 6502 put back in passed, and the 65C02 code
then ran on a NMOS 6502. The same text crt0_loader.s includes is assembled
here with the firmware bytes and MACHID of each machine, and run as a NMOS
6502 and as a 65C02: exit 0 = fits, 1 = unfit, 2 = nmos.

sim65 2.18 gives the NMOS decimal flags on its 65C02 too, so the cc65 master
simulator is required; its absence is a skip, not a pass.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))
ENV = {**os.environ, 'CC65_HOME': str(HEAD / 'share/cc65')}

HARNESS = r'''
        .export _main
_main:  lda     #FBB3V
        sta     $FBB3
        lda     #FBC0V
        sta     $FBC0
        lda     #MACHIDV
        sta     $BF98
        .include "machine_check.inc"
        lda     #0
        .byte   $2C
unfit:  lda     #1
        .byte   $2C
nmos:   lda     #2
        ldx     #0
        rts
'''

# Firmware ID bytes: $FBB3 $06 on every IIe/IIc/IIgs; $FBC0 $EA on the
# unenhanced IIe, $E0 on the enhanced IIe and the IIgs, $00 on the IIc.
# The II+ has $FBB3 = $EA. MACHID $B2 = IIe, 128 KB, 80 columns, clock.
FIT, UNFIT, NMOS = 0, 1, 2
CASES = [
    # (machine, $FBB3, $FBC0, MACHID, cpu, 65C02 edition, 6502 edition)
    ('enhanced IIe',               0x06, 0xE0, 0xB2, '65c02', FIT,   FIT),
    ('IIc',                        0x06, 0x00, 0xB2, '65c02', FIT,   FIT),
    ('enhanced IIe, 6502 fitted',  0x06, 0xE0, 0xB2, '6502',  NMOS,  FIT),
    ('IIc ROM, 6502',              0x06, 0x00, 0xB2, '6502',  NMOS,  FIT),
    ('unenhanced IIe',             0x06, 0xEA, 0xB2, '6502',  UNFIT, FIT),
    ('unenhanced IIe, 65C02 card', 0x06, 0xEA, 0xB2, '65c02', UNFIT, FIT),
    ('enhanced IIe, 64 KB',        0x06, 0xE0, 0x92, '65c02', UNFIT, UNFIT),
    ('enhanced IIe, 6502, 64 KB',  0x06, 0xE0, 0x92, '6502',  NMOS,  UNFIT),
    ('enhanced IIe, no 80 col',    0x06, 0xE0, 0xB0, '65c02', UNFIT, UNFIT),
    ('II+',                        0xEA, 0xEA, 0x40, '6502',  UNFIT, UNFIT),
]


class MachineCheck(unittest.TestCase):
    def setUp(self):
        if not (HEAD / 'bin/sim65').exists():
            self.skipTest('cc65 master not installed at %s' % HEAD)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / 'harness.s').write_text(HARNESS)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, fbb3, fbc0, machid, cpu, edition_6502):
        target = 'sim65c02' if cpu == '65c02' else 'sim6502'
        out = self.dir / ('%s_%02x%02x%02x_%d' % (target, fbb3, fbc0, machid, edition_6502))
        defines = ['FBB3V=%d' % fbb3, 'FBC0V=%d' % fbc0, 'MACHIDV=%d' % machid]
        if edition_6502:
            defines.append('A2_6502')
        cmd = [str(HEAD / 'bin/cl65'), '-t', target, '-I', str(ROOT / 'src'),
               '--asm-include-dir', str(ROOT / 'src')]
        for d in defines:
            cmd += ['--asm-define', d]
        subprocess.run(cmd + ['-o', str(out), str(self.dir / 'harness.s')],
                       check=True, capture_output=True, env=ENV)
        return subprocess.run([str(HEAD / 'bin/sim65'), str(out)], env=ENV).returncode

    def test_the_simulator_tells_the_processors_apart(self):
        """A 65C02 decimal sum sets N from its result, a NMOS 6502 does not:
        if the simulator ran both alike, every case below would prove nothing."""
        self.assertEqual(self.run_check(0x06, 0xE0, 0xB2, '6502', False), NMOS)
        self.assertEqual(self.run_check(0x06, 0xE0, 0xB2, '65c02', False), FIT)

    def test_each_machine(self):
        for machine, fbb3, fbc0, machid, cpu, enh, nmos in CASES:
            with self.subTest(machine=machine, edition='65C02'):
                self.assertEqual(self.run_check(fbb3, fbc0, machid, cpu, False), enh)
            with self.subTest(machine=machine, edition='6502'):
                self.assertEqual(self.run_check(fbb3, fbc0, machid, cpu, True), nmos)

    def test_the_launcher_uses_this_text(self):
        """crt0_loader.s includes the tested file and has no check of its own."""
        crt0 = (ROOT / 'src/crt0_loader.s').read_text()
        self.assertIn('.include        "machine_check.inc"', crt0)
        self.assertNotIn('$FBC0', crt0)
        self.assertNotIn('$FBB3', crt0)


if __name__ == '__main__':
    unittest.main()
