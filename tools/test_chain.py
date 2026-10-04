"""Execute the actual page-three launcher in sim65 with a failing ProDOS MLI.

The reset vector: A2FC's crt0 points it at its _exit ($400C), which the
launched program overwrites. Before 0.9.5 chain_load left it there, and
Ctrl-Reset in TAKE1.SYSTEM ran the picture bytes now at $400C. Here the
vector starts on a routine standing for A2FC's exit; the loaded program
does what the ROM does on Ctrl-Reset (check byte, then JMP ($03F2)). With
the 0.9.4 chain.s, measured: the OPEN already sees A2FC's vector (exit
code 1), and without that check the fake reset lands in A2FC's exit
(reset_hit 2, exit code 6). With the fix it reaches the monitor's OLDRST at
$FF59 (reset_hit 1), and every MLI call, failing or not, sees $FF59 / $5A.
"""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASM=r'''
.import _mock_call
.importzp ptr1
.export test_destruct, _handler, _callptr
.bss
_callptr: .res 2
save_x: .res 1
save_y: .res 1
.code
test_destruct:
 lda #$AA
 sta ptr1
 sta ptr1+1
 rts
; The MLI keeps X and Y (ProDOS 8 Technical Reference): so does the mock.
_handler:
 stx save_x
 sty save_y
 tsx
 lda $0101,x
 sta _callptr
 clc
 adc #3
 sta $0101,x
 lda $0102,x
 sta _callptr+1
 adc #0
 sta $0102,x
 lda _callptr
 ldx _callptr+1
 jsr _mock_call
 ldx save_x
 ldy save_y
 cmp #$65
 beq quit
 cmp #1
 rts
quit:
 pla
 pla
 rts
'''
C=r'''
#include <string.h>
extern void handler(void);
extern unsigned int callptr,chain_addr,chain_size;
void __fastcall__ chain_command(const char*);
void __fastcall__ chain_load(const char*);
static unsigned char fault,opened,read_ok,closed,quit_ok,bad;
#define SOFTEV ((unsigned char*)0x03F2)
#define RESET_HIT (*(unsigned char*)0x03E0)
/* What the ROM does on Ctrl-Reset, as the launched program: a valid check
 * byte, JMP ($03F2); else a cold start (reset_hit 3). */
static const unsigned char prog[]={0xAD,0xF3,0x03,0x49,0xA5,0xCD,0xF4,0x03,0xD0,0x03,
 0x6C,0xF2,0x03,0xA9,0x03,0x8D,0xE0,0x03,0x60};
static const unsigned char oldrst[]={0xA9,0x01,0x8D,0xE0,0x03,0x60};   /* at $FF59 */
static const unsigned char a2fc_exit[]={0xA9,0x02,0x8D,0xE0,0x03,0x60};/* at $3000 */
static unsigned char vector_ok(void){return SOFTEV[0]==0x59&&SOFTEV[1]==0xFF&&SOFTEV[2]==0x5A;}
/* fault 1 OPEN, 2 READ, 3 CLOSE, 4 low length byte short, 5 high length
 * byte wrong, 6 READ and CLOSE both fail */
unsigned char __fastcall__ mock_call(unsigned int ret){
 unsigned char cmd=*(unsigned char*)(ret+1);
 unsigned char*p=*(unsigned char**)(ret+2);
 unsigned char*name;
 if(cmd==0x65){quit_ok=1;return 0x65;}
 if(cmd==0xC8){
  opened=1;name=*(unsigned char**)(p+1);
  if(!vector_ok())bad=1;     /* set before the first byte is read */
  if(name[0]!=8 || memcmp(name+1,"/VOL/RUN",8))bad=1;
  p[5]=1;return fault==1;
 }
 if(cmd==0xCA){
  if(*(unsigned int*)(p+2)!=0x2000 || *(unsigned int*)(p+4)!=64)bad=1;
  *(unsigned int*)(p+6)=fault==4?63:fault==5?320:64;
  read_ok=1;memcpy((void*)0x2040,prog,sizeof prog);   /* past the command at $2006 */
  *(unsigned char*)0x2000=0x4C;*(unsigned int*)0x2001=0x2040;
  return fault==2||fault==6;
 }
 if(cmd==0xCC){++closed;if(p[0]!=1||p[1])bad=1;return fault==3||fault==6;}
 bad=1;return 1;
}
int main(void){
 *(unsigned char*)0xBF00=0x4C;*(unsigned int*)0xBF01=(unsigned int)handler;
 for(fault=0;fault<7;++fault){
  opened=read_ok=closed=quit_ok=bad=0;RESET_HIT=0;
  memcpy((void*)0x3000,a2fc_exit,sizeof a2fc_exit);memcpy((void*)0xFF59,oldrst,sizeof oldrst);
  SOFTEV[0]=0x00;SOFTEV[1]=0x30;SOFTEV[2]=0x30^0xA5;   /* A2FC's own, as crt0 sets it */
  chain_command("/VOL/PROGRAM");chain_addr=0x2000;chain_size=64;chain_load("/VOL/RUN");
  if(bad || !opened || quit_ok!=(fault!=0))return 1;
  if(!fault && (*(unsigned char*)0x2006!=12 || memcmp((void*)0x2007,"/VOL/PROGRAM",12)))return 2;
  if(fault==1 && (read_ok||closed))return 3;
  if(fault!=1 && closed!=1)return 4;   /* once opened, closed exactly once, even after a failed READ */
  if(!vector_ok())return 5;
  if(!fault && RESET_HIT!=1)return 6;   /* the fake Ctrl-Reset reached $FF59, not A2FC's exit */
  if(fault && RESET_HIT)return 7;       /* nothing ran after a refusal */
 }
 return 0;
}
'''
class Chain(unittest.TestCase):
 def test_native_paths_limits_and_close_failure(self):
  with tempfile.TemporaryDirectory(prefix='a2fc-chain-') as tmp:
   p=Path(tmp);(p/'host.s').write_text(ASM);(p/'test.c').write_text(C)
   (p/'chain.s').write_text((ROOT/'src/chain.s').read_text().replace('donelib', 'test_destruct'))
   target=Path(subprocess.check_output([shutil.which('cl65'),'--print-target-path'],text=True).strip())
   cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0', 'start = $4000, size = $BF00')
   (p/'test.cfg').write_text(cfg)
   for cpu in ('6502','65c02'):
    with self.subTest(cpu=cpu):
     subprocess.run([shutil.which('cl65'),'-t','sim65c02' if cpu=='65c02' else 'sim6502','--cpu',cpu,'-C',str(p/'test.cfg'),'-O','-o',str(p/'test'),str(p/'test.c'),str(p/'host.s'),str(p/'chain.s')],check=True)
     subprocess.run([shutil.which('sim65'),str(p/'test')],check=True,timeout=10)
class Crt0(unittest.TestCase):
 def test_exits_never_restore_a_saved_reset_vector(self):
  """A2FC's crt0 used to put back, on its way out, the vector it found at
  startup: A2FILE.SYSTEM's own, into the launcher's code that A2FC's
  pictures overwrite. Both crt0 copies now leave $FF59 (OLDRST, in ROM)."""
  import re
  for name in ('crt0.s','crt0_loader.s'):
   s=(ROOT/'src'/name).read_text()
   code='\n'.join(l.split(';')[0] for l in s.splitlines())
   self.assertNotIn('rvsave',code,name)
   self.assertRegex(code,r'exit:\s+ldx\s+#\$59\s+lda\s+#\$FF\s+jsr\s+(reset|setsoftev)',name)
if __name__=='__main__':unittest.main()
