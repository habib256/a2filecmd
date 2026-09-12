"""Actual Purplesoft loader: exact planes, malformed pairs and I/O failures."""
import subprocess,tempfile,unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT
HARNESS=PREFIX+r'''
static int fail,opened,closed,shown,moved,rebuilt,waited,mode_seen;
static FILE* bad;
static int err(FILE* f){return f==bad || ferror(f);}
#define ferror err
#include "src/plugins/purple.c"
#undef ferror
unsigned char host_page[8192];
static unsigned char aux[8192];
void pu_prepare(void){}
void pu_aux_move(void){memcpy(aux,host_page,8192);++moved;}
void pu_show(unsigned char mode){++shown;mode_seen=mode;}
void pu_restore(void){}
static char rebuild(void){++rebuilt;return 1;}
static char waitkey(void){++waited;return 27;}
static FILE* op(const char* p,const char* m){++opened;if(strcmp(m,"rb"))abort();return fopen(p,m);}
static size_t rd(void* p,size_t z,size_t n,FILE* f){
 if((fail==1 && opened==1)||(fail==2 && opened==2)||(fail==5 && n==1)){
  bad=f;return 0;
 }
 return fread(p,z,n,f);
}
static int closeit(FILE* f){int r=fclose(f);++closed;return fail==closed+2?EOF:r;}
int main(int argc,char** argv){
 static struct A2fcApi a;static struct Entry e;
 static char other[81],note[81],reselect[81];static unsigned char copy[512];
 if(__plugin_header.desc[sizeof __plugin_header.desc-1])abort();
 fail=atoi(argv[2]);memset(aux,0xD7,sizeof aux);memset(host_page,0xEE,sizeof host_page);
 strcpy(e.name,"A.FOTO1");a.full=argv[1];a.other_full=other;a.note=note;a.reselect=reselect;a.selected=&e;
 a.strlen=strlen;a.strcpy=strcpy;a.fopen=op;a.fread=rd;a.fclose=closeit;a.copy_buf=copy;a.ram_format=rebuild;a.media_wait=waitkey;
 plugin_entry(&a);
 printf("%d %d %d %d %d %d %d\n",opened,closed,shown,moved,rebuilt,waited,mode_seen);
 fwrite(host_page,1,8192,stdout);fwrite(aux,1,8192,stdout);
 return 0;
}
'''
def planes(mode=5):
 a=bytearray((i*37+11)&255 for i in range(8192));a[0x79:0x7b]=bytes([mode,83])
 return bytes(a),bytes((i*19+3+mode)&255 for i in range(8192))
class Purple(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='purple-');cls.d=Path(cls.tmp.name)
  (cls.d/'test.c').write_text(HARNESS);cls.exe=cls.d/'test'
  subprocess.run(['cc','-Wno-incompatible-function-pointer-types','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.d/'test.c'),'-o',str(cls.exe)],check=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_pair(self,a,b,fail=0,selected=1):
  paths=[self.d/'A.FOTO1',self.d/'A.FOTO2']
  for p,data in zip(paths,(a,b)):
   if data is None:p.unlink(missing_ok=True)
   else:p.write_bytes(data)
  r=subprocess.run([str(self.exe),str(paths[selected-1]),str(fail)],capture_output=True,check=True)
  stats,pages=r.stdout.split(b'\n',1)
  for p,data in zip(paths,(a,b)):
   self.assertEqual(p.read_bytes() if p.exists() else None,data)
  return list(map(int,stats.split())),pages[:8192],pages[8192:]
 def test_all_modes_and_both_entry_names(self):
  for mode in range(10):
   for selected in (1,2):
    a,b=planes(mode);s,main,aux=self.run_pair(a,b,selected=selected)
    self.assertEqual(s,[2,2,1,int(mode>=5),int(mode>=5),1,mode]);self.assertEqual(main,b)
    self.assertEqual(aux,a if mode>=5 else bytes([0xD7])*8192)
 def test_invalid_first_never_touches_aux(self):
  a,b=planes();wrong=bytearray(a);wrong[0x7a]=0;mode=bytearray(a);mode[0x79]=10
  for data in (None,a[:-1],a+b'X',bytes(wrong),bytes(mode)):
   s,_,aux=self.run_pair(data,b);self.assertEqual(s[2:6],[0,0,0,0]);self.assertEqual(aux,bytes([0xD7])*8192)
 def test_missing_second_never_touches_aux(self):
  s,_,aux=self.run_pair(planes()[0],None);self.assertEqual(s[2:6],[0,0,0,0]);self.assertEqual(aux,bytes([0xD7])*8192)
 def test_damaged_second_rebuilds_after_aux_write(self):
  a,b=planes()
  for data in (b[:-1],b+b'X'):
   s,_,aux=self.run_pair(a,data);self.assertEqual(s[2:6],[0,1,1,0]);self.assertEqual(aux,a)
 def test_read_eof_and_close_errors(self):
  a,b=planes()
  for fail in range(1,6):
   s,_,aux=self.run_pair(a,b,fail);dirty=int(fail in (2,4))
   self.assertEqual(s[2:6],[0,dirty,dirty,0]);self.assertEqual(aux,a if dirty else bytes([0xD7])*8192)
if __name__=='__main__':unittest.main()
