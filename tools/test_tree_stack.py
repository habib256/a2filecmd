"""Run the exact recursive-traversal stack guard for every 16-bit C sp."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TreeStack(unittest.TestCase):
 def test_all_stack_addresses(self):
  routine=(ROOT/'src/overlay.s').read_text().split('_tree_stack_ok:\n',1)[1]
  asm='''.importzp sp
.export _check
__HIMEM__ = $BF00
__STACKSIZE__ = $C0
.bss
saved: .res 2
.code
_check:
 pha
 lda sp
 sta saved
 lda sp+1
 sta saved+1
 pla
 sta sp
 stx sp+1
 jsr guard
 ldy saved
 sty sp
 ldy saved+1
 sty sp+1
 rts
guard:
'''+routine
  c='''unsigned char __fastcall__ check(unsigned int p);
int main(void){unsigned int p=0;do{if(check(p)!=(p>=0xBE90))return 1;}while(++p);return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='tree-guard-') as t:
   t=Path(t);(t/'guard.s').write_text(asm);(t/'test.c').write_text(c)
   for cpu in ['6502','65c02']:
    with self.subTest(cpu=cpu):
     subprocess.run([shutil.which('cl65'),'-t','sim6502','--cpu',cpu,'-O','-o',str(t/'test'),str(t/'test.c'),str(t/'guard.s')],check=True,capture_output=True)
     subprocess.run([shutil.which('sim65'),str(t/'test')],check=True,timeout=15)
if __name__=='__main__':unittest.main()
