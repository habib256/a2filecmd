"""Run the actual launch-prefix assembly against stale/malformed SYS paths."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_chain import ASM
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <string.h>
extern void handler(void),set_boot_prefix(void);
static char current[65];
static unsigned char fault,sets,online;
unsigned char __fastcall__ mock_call(unsigned int ret){
 unsigned char cmd=*(unsigned char*)(ret+1);
 unsigned char*p=*(unsigned char**)(ret+2);
 unsigned char*b=*(unsigned char**)(p+1);
 if(cmd==0xC7){if(fault==1)return 1;b[0]=strlen(current);memcpy(b+1,current,b[0]);return 0;}
 if(cmd==0xC6){++sets;if(fault==2)return 1;memcpy(current,b+1,b[0]);current[b[0]]=0;return 0;}
 if(cmd==0xC5){++online;b=*(unsigned char**)(p+2);b[0]=4;memcpy(b+1,"BOOT",4);return fault==3;}
 return 1;
}
static void path(const char*p){*(unsigned char*)0x280=strlen(p);strcpy((char*)0x281,p);sets=online=0;fault=0;}
int main(void){
 *(unsigned char*)0xBF00=0x4C;*(unsigned int*)0xBF01=(unsigned int)handler;*(unsigned char*)0xBF30=0x60;
 strcpy(current,"/SOURCE/WORK");path("/BOOT/A2FILE.SYSTEM");set_boot_prefix();
 if(strcmp(current,"/BOOT/")||sets!=1||online)return 1;
 path("/DISK/SUB/a2file.system");set_boot_prefix();if(strcmp(current,"/DISK/SUB/"))return 2;
 path("/OTHER/OTHER.SYSTEM");set_boot_prefix();if(strcmp(current,"/DISK/SUB/")||sets)return 3;
 path("A2FILE.SYSTEM");set_boot_prefix();if(strcmp(current,"/DISK/SUB/")||sets)return 4;
 path("/BOOT/A2FILE.SYSTEM");*(unsigned char*)0x280=255;set_boot_prefix();if(sets)return 5;
 path("/BOOT/A2FILE.SYSTEM");fault=1;set_boot_prefix();if(sets||online)return 6;
 path("/BOOT/A2FILE.SYSTEM");fault=2;set_boot_prefix();if(strcmp(current,"/DISK/SUB/"))return 7;
 current[0]=0;path("");set_boot_prefix();if(strcmp(current,"/BOOT")||online!=1)return 8;
 current[0]=0;path("");fault=3;set_boot_prefix();if(current[0]||sets)return 9;
 return 0;
}
'''
class LoaderPrefix(unittest.TestCase):
 def test_native_prefix_resolution(self):
  with tempfile.TemporaryDirectory(prefix='a2fc-prefix-') as tmp:
   p=Path(tmp);(p/'host.s').write_text(ASM);(p/'test.c').write_text(C)
   (p/'prefix.s').write_text((ROOT/'src/loader_mli.s').read_text())
   target=Path(subprocess.check_output([shutil.which('cl65'),'--print-target-path'],text=True).strip())
   cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0','start = $4000, size = $BFF0')
   (p/'test.cfg').write_text(cfg)
   for target in ('sim6502','sim65c02'):
    with self.subTest(target=target):
     subprocess.run([shutil.which('cl65'),'-t',target,'-C',str(p/'test.cfg'),'-O','-o',str(p/'test'),str(p/'test.c'),str(p/'host.s'),str(p/'prefix.s')],check=True)
     subprocess.run([shutil.which('sim65'),str(p/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
