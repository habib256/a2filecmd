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
# src/loader.c itself, its screen calls stubbed out, reading a host file under
# sim65. The program lives at $C000: the launcher fills $1000-$1BFF and
# $4000-$BEFF. An image starting with RTS at $4000 returns into main, which
# then exits 0 ("jumped"); a refused image exits 1. sim65's read does not set
# _oserror: the fread wrapper sets it as cc65's apple2 rwcommon.s does after
# each ProDOS READ -- 0 when bytes came, $4C at the end of the file, the
# error code on a failure (and fread makes no READ once its error flag is
# set).
LOADER_C=r'''
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <errno.h>
#define VIDEOMODE_80COL 0
static unsigned videomode(unsigned m){return m;}
static void clrscr(void){}
static void chlinexy(unsigned char x,unsigned char y,unsigned char l){}
static void cputcxy(unsigned char x,unsigned char y,char c){}
static unsigned char revers(unsigned char on){return 0;}
static void gotoxy(unsigned char x,unsigned char y){}
static void cputsxy(unsigned char x,unsigned char y,const char* s){}
static void cputs(const char* s){}
static int cprintf(const char* f,...){return 0;}
static char cgetc(void){return 0;}
void set_boot_prefix(void){}
static char* code_file;
static unsigned char calls,fault;
static size_t test_fread(void* p,size_t s,size_t n,FILE* f){
 size_t got;
 if(fault && ++calls==fault)close(fileno(f));   /* a read error from that read on */
 if(ferror(f))return 0;
 got=fread(p,s,n,f);
 _oserror=got?0:ferror(f)?0x27:0x4C;
 return got;
}
#define CODE_FILE code_file
#define fread test_fread
#define main loader_main
@LOADER@
#undef main
int main(int argc,char** argv){
 code_file=argv[1];fault=atoi(argv[2]);
 return loader_main();
}
'''
class LoaderImage(unittest.TestCase):
 def test_launcher_jumps_only_into_a_whole_image(self):
  loader=(ROOT/'src/loader.c').read_text()
  self.assertEqual(loader.count('#include <conio.h>'),1)
  self.assertEqual(loader.count('#include <errno.h>'),1)
  # conio has no sim65 library; errno.h is already included above the wrapper.
  src=LOADER_C.replace('@LOADER@',loader.replace('#include <conio.h>','').replace('#include <errno.h>',''))
  with tempfile.TemporaryDirectory(prefix='a2fc-loader-') as tmp:
   p=Path(tmp);(p/'test.c').write_text(src)
   target=Path(subprocess.check_output([shutil.which('cl65'),'--print-target-path'],text=True).strip())
   cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0','start = $C000, size = $3FF0')
   cfg=cfg.replace('value = $0800; # 2k stack','value = $0400;')
   (p/'test.cfg').write_text(cfg)
   stage=bytes(range(256))*12
   body=b'\x60'+bytes(0x6FFF)
   cases=[('whole image',stage+body,0,0),
          ('short language-card stage',stage[:0x800],0,1),
          ('read error on the third chunk',stage+body,4,1),
          ('read error on the language-card stage',stage+body,1,1),
          ('image past $BEFF',stage+b'\x60'+bytes(0x7F00),0,1)]
   for tgt in ('sim6502','sim65c02'):
    subprocess.run([shutil.which('cl65'),'-t',tgt,'-C',str(p/'test.cfg'),'-O','-o',str(p/'loader'),str(p/'test.c')],check=True)
    for label,data,fault,want in cases:
     with self.subTest(target=tgt,case=label):
      (p/'CODE').write_bytes(data)
      r=subprocess.run([shutil.which('sim65'),str(p/'loader'),str(p/'CODE'),str(fault)],timeout=20)
      self.assertEqual(r.returncode,want)
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
