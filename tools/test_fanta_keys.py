"""Real Fantavision pause/key assembly on both CPUs; engine calls instrumented."""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class FantaKeys(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='fanta-keys-');p=Path(cls.tmp.name)
  source=(ROOT/'src/fanta/fanta.s').read_text()
  keys=source[source.index('keys:'):source.index('; These helpers remain callable')].replace('.segment "FCOLD"', '.code')
  asm='''
.macpack longbranch
.export _run, _steps, _escaped, _done, _mode, _delay, _slide, _fv_count
.import _get_next
KBD=$C000
KBDSTRB=$C010
HISCR=$C055
LOWSCR=$C054
.bss
_steps: .res 1
_escaped: .res 1
_done: .res 1
_mode:
mode: .res 1
_delay:
delay: .res 1
_slide:
slide: .res 1
_fv_count:
fv_count: .res 1
fv_shown: .res 1
fv_vkey: .res 1
progress: .res 1
.code
_run: lda #$A0
sta KBD
lda #$20
sta fv_shown
lda #1
sta mode
sta fv_count
jmp keys
getkey: jmp _get_next
fv_next: inc _steps
lda #0
sta fv_vkey
inc progress
lda progress
cmp #3
bne :+
lda #1
sta fv_vkey
lda #0
sta progress
: lda _done
bne @end
lda fv_shown
eor #$60
sta fv_shown
lda #0
@end: rts
back: lda #1
sta _escaped
pla
pla
rts
'''+keys
  (p/'keys.s').write_text(asm)
  (p/'main.c').write_text('''
#include <stdio.h>
#include <stdlib.h>
extern unsigned char steps,escaped,done,mode,delay,slide,fv_count;
static char* keys;
unsigned char get_next(void){return (*keys ? *keys++ : ' ')|128;}
void run(void);
int main(int argc,char**argv){keys=argv[1];done=atoi(argv[2]);*(unsigned char*)0xC054=0;*(unsigned char*)0xC055=0;run();
printf("%u %u %u %u %u %u %u %u\\n",steps,escaped,mode,delay,slide,fv_count,
*(unsigned char*)0xC054,*(unsigned char*)0xC055);return 0;}
''')
  cls.exes=[]
  for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
   exe=p/cpu
   subprocess.run(['cl65','-t',target,'--cpu',cpu,'-o',str(exe),str(p/'main.c'),str(p/'keys.s')],check=True,capture_output=True,cwd=p)
   cls.exes.append(exe)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_steps_stay_paused_and_preserve_other_controls(self):
  for exe in self.exes:
   for keys,done,want in (('\x15\x15\r ',0,'3 0 1 0 0 1 32 64'),
                          ('\t9s\x15 ',0,'1 0 0 9 1 0 0 64'),
                          ('\x15\r ',1,'2 0 1 0 0 1 0 0'),
                          ('\x15\x1b',0,'1 1 1 0 0 1 0 64'),
                          ('x ',0,'0 0 1 0 0 1 0 0'),
                          ('N ',0,'3 0 1 0 0 1 0 64'),
                          ('nn ',0,'6 0 1 0 0 1 32 64'),
                          ('\t9sN ',0,'3 0 0 9 1 0 0 64'),
                          ('N ',1,'1 0 1 0 0 1 0 0'),
                          ('N\x1b',0,'3 1 1 0 0 1 0 64')):
    r=subprocess.run(['sim65','-x','1000000',str(exe),keys,str(done)],check=True,capture_output=True,text=True)
    self.assertEqual(r.stdout.strip(),want,(exe.name,keys))

if __name__=='__main__':unittest.main()
