"""Run the production read-only command gate under sim65 on both CPUs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "src/a2fc_plugin.h"
unsigned char active;
struct Panel panels[2];
const char msg_roimg[]="Read-only disk.";
static unsigned int called, refused;
static unsigned char seen;char input[17],note[80];
void message(const char* s){assert(s==msg_roimg);++refused;}
void overlay_run(const char* name,unsigned char arg){
 assert(!strcmp(name,"DOSVIEW")||!strcmp(name,"IDENT"));++called;seen=arg;note[0]=1;
 /* A big overlay may reread either panel before returning. */
 memset(panels,0,sizeof panels);
}
unsigned char __fastcall__ fs_key(unsigned char key);
int main(void){
 unsigned int k;unsigned char fs,handled,allowed,blocked;
 assert(sizeof(struct Panel)==98);
 for(active=0;active<2;++active)for(fs=0;fs<3;++fs)for(k=0;k<256;++k){
  memset(panels,0,sizeof panels);panels[active].fs=fs;
  panels[!active].fs=(fs==0?2:0);called=refused=0;
  allowed=fs==2&&(k==13||k=='T'||k=='t'||k=='H'||k=='h'||k=='I'||k=='i');
  blocked=fs&&strchr("rkaldxewthim",(unsigned char)(k|32))!=0;
  handled=fs_key(k);
  if(handled!=(allowed||blocked)){fprintf(stderr,"fs=%u panel=%u key=%u got=%u expected=%u\n",fs,active,k,handled,allowed||blocked);return 2;}
  assert(called==allowed);assert(refused==(!allowed&&blocked));
  if(called)assert(seen==((k=='i'||k=='I')?13:(unsigned char)(k&0xDF)));
 }
 return 0;
}
'''


DISPATCH = r'''
#include <assert.h>
#include <string.h>
#include "src/a2fc_plugin.h"
unsigned char active;struct Panel panels[2];char input[17],note[80];
const char msg_roimg[]="Read-only disk.";
static unsigned char mode,calls,key;
void message(const char* s){(void)s;}
void overlay_run(const char* name,unsigned char arg){
 ++calls;
 if(calls==1){
  assert(!strcmp(name,(key=='T'||key=='H')?"DOSVIEW":"IDENT"));assert(arg==key);
  if(mode==0)strcpy(input,"NEWSPAN");else if(mode==3)strcpy(input,"DOSVIEW");else if(mode==2)strcpy(note,"Source read error.");
 }else if(mode==0||mode==3){assert(calls==2);assert(!strcmp(name,mode==0?"NEWSPAN":"DOSVIEW"));assert(arg==13);}
 else if(mode==1){
  if(calls==2){assert(!strcmp(name,key==13?"DOSVIEW":"OPEN"));assert(arg==key);if(key!=13)strcpy(input,"TEXT");}
  else{assert(calls==3);assert(!strcmp(name,"TEXT"));assert(arg==13);}
 }else assert(0);
}
void __fastcall__ identify_viewer(unsigned char);
int main(void){
 for(mode=0;mode<4;++mode){
  for(key=13;key<90;++key){
   if(key!=13 && key!='O' && key!='I')continue;
   strcpy(input,"DELETE");strcpy(note,"old message");calls=0;identify_viewer(key);
   assert(calls==(mode==0||mode==3?2:mode==2?1:key==13?2:3));
  }
 }
 mode=1;key='T';calls=0;identify_viewer(key);assert(calls==1);
 key='H';calls=0;identify_viewer(key);assert(calls==1);return 0;
}
'''

class Commands(unittest.TestCase):
    def test_all_keys_filesystems_panels_and_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):
            self.skipTest('cc65/sim65 unavailable')
        with tempfile.TemporaryDirectory(prefix='dos-fs-keys-') as tmp:
            tmp=Path(tmp);source=tmp/'test.c';source.write_text(HARNESS)
            for target,cpu in (('sim6502','6502'),('sim65c02','65c02')):
                path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
                config=tmp/(target+'.cfg')
                config.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace(
                    '\n    RODATA:', '\n    LC: load = MAIN, type = ro;\n    RODATA:',1))
                exe=tmp/target
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-C',str(config),
                                '-I',str(ROOT),'-o',str(exe),str(source),str(ROOT/'src/fs_keys.s')],
                               check=True,capture_output=True)
                result=subprocess.run(['sim65',str(exe)],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                source.write_text(DISPATCH)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(source),str(ROOT/'src/fs_keys.s')],check=True,capture_output=True)
                result=subprocess.run(['sim65',str(exe)],capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                source.write_text(HARNESS)


if __name__=='__main__':
    unittest.main()
