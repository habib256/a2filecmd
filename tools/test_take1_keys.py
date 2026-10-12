"""Real Take 1 show/pause/key assembly on both CPUs, with scripted keyboard reads."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Take1Keys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='take1-keys-')
        p = Path(cls.tmp.name)
        source = (ROOT / 'src/take1/take1.s').read_text()
        show = source[source.index('t1_show:'):source.index('; A fade\'s D(A)')].replace('.segment "TXC6"', '.code')
        keys = source[source.index('\nkeys:') + 1:source.index('; A $FC element:')]
        # Preserve all real branches and flag handling; sim65 has no keyboard
        # device, so only the memory-mapped reads are supplied by the driver.
        keys = keys.replace('lda     KBD', 'jsr     _next_key\n        ora     #0')
        asm = '''
.export _run, _frame, _step, _mode, _escaped
.import _next_key, _record
KBDSTRB=$C010
HISCR=$C055
LOWSCR=$C054
.bss
_frame: .res 1
_step:
step: .res 1
_mode:
mode: .res 1
_escaped: .res 1
saved: .res 1
.code
_run: tsx
stx saved
lda #1
sta mode
@loop: lda _frame
and #1
beq @first
lda #$40
bne @show
@first: lda #$20
@show: jsr t1_show
jsr _record
inc _frame
lda _frame
cmp #5
bne @loop
rts
back: ldx saved
txs
inc _escaped
rts
'''+show+keys
        (p / 'keys.s').write_text(asm)
        (p / 'main.c').write_text('''
#include <stdio.h>
extern unsigned char frame, step, mode, escaped;
static char *keys;
unsigned char next_key(void) {
  printf("K%u,%u,%u;",frame,step,mode);
  return *keys ? *keys++ | 128 : 0;
}
void record(void) {
  printf("F%u,%u,%u;",frame,step,mode);
}
void run(void);
int main(int argc, char **argv) {
  keys=argv[1]; run();
  printf("E%u,%u,%u,%u\\n",frame,step,mode,escaped);
  return 0;
}
''')
        cls.exes = []
        for cpu, target in (('6502', 'sim6502'), ('65c02', 'sim65c02')):
            exe = p / cpu
            subprocess.run(['cl65', '-t', target, '--cpu', cpu, '-o', str(exe),
                            str(p / 'main.c'), str(p / 'keys.s')], check=True,
                           capture_output=True, cwd=p)
            cls.exes.append(exe)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, keys, want):
        for exe in self.exes:
            r = subprocess.run(['sim65', '-x', '1000000', str(exe), keys],
                               check=True, capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), want, (exe.name, repr(keys)))

    def test_steps_stop_at_next_show_tab_keeps_pause_space_resumes(self):
        self.check(' \x15\r\tx ',
                   'K0,0,1;K0,0,1;F0,1,1;K1,1,1;F1,1,1;'
                   'K2,1,1;K2,1,0;K2,1,0;F2,0,0;'
                   'K3,0,0;F3,0,0;K4,0,0;F4,0,0;E5,0,0,0')

    def test_step_keys_outside_pause_are_ignored(self):
        self.check('\x15\rx',
                   'K0,0,1;F0,0,1;K1,0,1;F1,0,1;K2,0,1;F2,0,1;'
                   'K3,0,1;F3,0,1;K4,0,1;F4,0,1;E5,0,1,0')

    def test_escape_unwinds_from_step_pause(self):
        self.check(' \x15\x1b',
                   'K0,0,1;K0,0,1;F0,1,1;K1,1,1;E1,1,1,1')

    def test_space_can_pause_again_after_resuming_step(self):
        self.check(' \x15  \r ',
                   'K0,0,1;K0,0,1;F0,1,1;K1,1,1;F1,0,1;'
                   'K2,0,1;K2,0,1;F2,1,1;K3,1,1;F3,0,1;'
                   'K4,0,1;F4,0,1;E5,0,1,0')


if __name__ == '__main__':
    unittest.main()
