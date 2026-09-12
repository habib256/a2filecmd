"""Execute the actual page-three launcher in sim65 with a failing ProDOS MLI."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASM=r'''
.import _mock_call
.importzp ptr1
.export test_destruct, _handler, _callptr
.bss
_callptr: .res 2
.code
test_destruct:
 lda #$AA
 sta ptr1
 sta ptr1+1
 rts
_handler:
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
unsigned char __fastcall__ mock_call(unsigned int ret){
 unsigned char cmd=*(unsigned char*)(ret+1);
 unsigned char*p=*(unsigned char**)(ret+2);
 unsigned char*name;
 if(cmd==0x65){quit_ok=1;return 0x65;}
 if(cmd==0xC8){
  opened=1;name=*(unsigned char**)(p+1);
  if(name[0]!=8 || memcmp(name+1,"/VOL/RUN",8))bad=1;
  p[5]=1;return fault==1;
 }
 if(cmd==0xCA){
  if(*(unsigned int*)(p+2)!=0x2000 || *(unsigned int*)(p+4)!=64)bad=1;
  *(unsigned int*)(p+6)=fault==4?63:64;
  read_ok=1;*(unsigned char*)0x2000=0x60;return fault==2;
 }
 if(cmd==0xCC){closed=1;return fault==3;}
 bad=1;return 1;
}
int main(void){
 *(unsigned char*)0xBF00=0x4C;*(unsigned int*)0xBF01=(unsigned int)handler;
 for(fault=0;fault<5;++fault){
  opened=read_ok=closed=quit_ok=bad=0;
  chain_command("/VOL/PROGRAM");chain_addr=0x2000;chain_size=64;chain_load("/VOL/RUN");
  if(bad || !opened || quit_ok!=(fault!=0))return 1;
  if(!fault && (*(unsigned char*)0x2006!=12 || memcmp((void*)0x2007,"/VOL/PROGRAM",12)))return 2;
  if(fault==1 && (read_ok||closed))return 3;
  if((fault==2 || fault==4) && closed)return 4;
  if(fault==3 && !closed)return 5;
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
   cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0', 'start = $4000, size = $BFF0')
   (p/'test.cfg').write_text(cfg)
   for cpu in ('6502','65c02'):
    with self.subTest(cpu=cpu):
     subprocess.run([shutil.which('cl65'),'-t','sim65c02' if cpu=='65c02' else 'sim6502','--cpu',cpu,'-C',str(p/'test.cfg'),'-O','-o',str(p/'test'),str(p/'test.c'),str(p/'host.s'),str(p/'chain.s')],check=True)
     subprocess.run([shutil.which('sim65'),str(p/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
