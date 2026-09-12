"""Execute the real preference save/load code with filesystem fault injection."""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/stat.h>
#define PATH_LEN 64
#define SORT_MODES 3
static struct {char path[64];} panels[2];
static char cfg_path[64],note[80];
static unsigned char sort_mode=1,active=1,gfi[18],_oserror,_filetype;
static unsigned int _auxtype;
static const char* fault;
static int phase,renames,installed;
static int isfault(const char* s){return !strcmp(fault,s);}
static unsigned char file_info(const char* p){
 struct stat st;memset(gfi,0,sizeof gfi);
 if((strstr(p,".BAK") && isfault("bak_stat")) || (strstr(p,".CFG") && isfault("old_stat"))) {_oserror=0x27;return 0;}
 if(stat(p,&st)){_oserror=errno==ENOENT?0x46:0x27;return 0;}
 gfi[7]=1;gfi[3]=isfault("locked")?1:0xC3;gfi[4]=S_ISDIR(st.st_mode)?15:4;_oserror=0;return 1;
}
static FILE* cfopen(const char* p,const char* m){
 phase=strstr(p,".TMP")?(!strcmp(m,"wb")?2:3):(installed?4:1);
 if(isfault("open_temp") && phase==2)return NULL;
 return fopen(p,m);
}
static size_t cfread(void* p,size_t s,size_t n,FILE* f){
 if((phase==1 && isfault("old_read")) || (phase==3 && isfault("verify_read")) || (phase==4 && isfault("install_read")))return 0;
 return fread(p,s,n,f);
}
static int cferror(FILE* f){
 return ((phase==1 && isfault("old_read")) || (phase==3 && isfault("verify_read")) || (phase==4 && isfault("install_read"))) || ferror(f);
}
static int cfclose(FILE* f){
 int r=fclose(f);
 if((phase==1 && isfault("old_close")) || (phase==2 && isfault("temp_close")) || (phase==3 && isfault("verify_close")) || (phase==4 && isfault("install_close")))return EOF;
 return r;
}
static size_t cfwrite(const void* p,size_t z,size_t n,FILE* f){
 unsigned char b[256];
 if(isfault("short_write") || isfault("remove_temp"))return fwrite(p,z,n/2,f);
 if(isfault("corrupt_write")){memcpy(b,p,n);b[0]^=1;return fwrite(b,z,n,f);}
 return fwrite(p,z,n,f);
}
static int copen(const char* p,int flags){
 assert((flags&(O_CREAT|O_EXCL))==(O_CREAT|O_EXCL));
 if(isfault("create")){errno=ENOSPC;return -1;}
 return open(p,flags,0600);
}
static int cclose(int fd){int r=close(fd);return isfault("create_close")?-1:r;}
static int cren(const char* a,const char* b){
 ++renames;
 if((renames==1 && isfault("rename_backup")) || (renames==2 && (isfault("rename_install")||isfault("rename_restore"))) || (renames==3 && isfault("rename_restore")))return -1;
 if(access(b,F_OK)==0){errno=EEXIST;return -1;}
 if(rename(a,b))return -1;
 if(strstr(a,".TMP"))installed=1;
 return (isfault("after_install") && renames==2)?-1:0;
}
static int crem(const char* p){
 if((strstr(p,".BAK") && isfault("remove_backup")) || (strstr(p,".TMP") && isfault("remove_temp")))return -1;
 return remove(p);
}
#define fopen cfopen
#define fread cfread
#define fwrite cfwrite
#define fclose cfclose
#define ferror cferror
#define open copen
#define close cclose
#define rename cren
#define remove crem
#define CONFIG_STATE (&host_config)
static struct ConfigState host_config;
#include "src/config.h"
int main(int argc,char** argv){
 strcpy(cfg_path,argv[1]);fault=argv[2];strcpy(panels[0].path,"/NEW/LEFT");strcpy(panels[1].path,"/NEW/RIGHT");
 if(argc>3){load_config();printf("%s|%s|%u|%u|%s\n",panels[0].path,panels[1].path,sort_mode,active,note);}
 else printf("%u|%s\n",save_config(),note);
 return 0;
}
'''.replace('#include <stdio.h>','#include <assert.h>\n#include <stdio.h>')
OLD=b'/OLD/LEFT\r/OLD/RIGHT\rS0A0\r'
NEW=b'/NEW/LEFT\r/NEW/RIGHT\rS1A1\r'
class Config(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='cf-',dir='/tmp');cls.root=Path(cls.tmp.name)
  c=cls.root/'test.c';c.write_text(C);cls.exe=cls.root/'test'
  subprocess.run(['cc','-std=c99','-I',str(ROOT),str(c),'-o',str(cls.exe)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,fault='',old=OLD,extra=None,load=False):
  d=Path(tempfile.mkdtemp(prefix='c-',dir=self.root));cfg=d/'A2FILE.CFG'
  if old is not None:cfg.write_bytes(old)
  for name,data in (extra or {}).items():(d/name).write_bytes(data)
  out=subprocess.check_output([self.exe,cfg,fault]+(['load'] if load else []),text=True)
  return out,{p.name:p.read_bytes() for p in d.iterdir()}
 def test_replace_and_first_save(self):
  for old in (OLD,None):
   out,files=self.run_case(old=old);self.assertTrue(out.startswith('1|'));self.assertEqual(files,{'A2FILE.CFG':NEW})
 def test_faults_preserve_old_bytes(self):
  for fault in ('bak_stat','old_stat','locked','old_read','old_close','open_temp','short_write','corrupt_write','temp_close','verify_read','verify_close','create','create_close','rename_backup','rename_install','rename_restore','after_install','install_read','install_close','remove_backup','remove_temp'):
   with self.subTest(fault=fault):
    out,files=self.run_case(fault);self.assertTrue(out.startswith('0|'),out)
    self.assertIn(OLD,files.values(),files)
    for name,data in files.items():
     if name=='A2FILE.CFG':self.assertIn(data,(OLD,NEW))
 def test_existing_recovery_files_are_untouched(self):
  for name in ('A2FILE.TMP','A2FILE.BAK'):
   out,files=self.run_case(extra={name:b'personal bytes'})
   self.assertTrue(out.startswith('0|'));self.assertEqual(files,{'A2FILE.CFG':OLD,name:b'personal bytes'})
 def test_load_is_all_or_nothing(self):
  for bad in (b'',b'/OK\r',b'/OK\r/BAD\rS0A2\r',b'/'+b'X'*64+b'\r/B\rS0A0\r',OLD+b'extra',OLD.replace(b'S0',b'S9')):
   out,files=self.run_case(old=bad,load=True);self.assertTrue(out.startswith('/NEW/LEFT|/NEW/RIGHT|1|1|'),out);self.assertEqual(files,{'A2FILE.CFG':bad})
  for fault in ('old_read','old_close','old_stat'):
   out,files=self.run_case(fault,load=True);self.assertTrue(out.startswith('/NEW/LEFT|/NEW/RIGHT|1|1|'));self.assertEqual(files,{'A2FILE.CFG':OLD})
 def test_backup_recovery_is_read_only(self):
  out,files=self.run_case(old=None,extra={'A2FILE.BAK':OLD},load=True)
  self.assertTrue(out.startswith('/OLD/LEFT|/OLD/RIGHT|0|0|'));self.assertEqual(files,{'A2FILE.BAK':OLD})
 def test_valid_config_and_empty_volume_panels(self):
  for value,want in ((OLD,'/OLD/LEFT|/OLD/RIGHT|0|0|'),(b'\r\rS2A1\r','||2|1|')):
   out,files=self.run_case(old=value,load=True);self.assertTrue(out.startswith(want),out);self.assertEqual(files,{'A2FILE.CFG':value})
 def test_malformed_existing_config_is_not_replaced(self):
  out,files=self.run_case(old=b'personal bytes');self.assertTrue(out.startswith('0|'));self.assertEqual(files,{'A2FILE.CFG':b'personal bytes'})
if __name__=='__main__':unittest.main()
