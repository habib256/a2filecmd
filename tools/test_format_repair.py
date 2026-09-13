"""Execute shipped FIXTYPES/IDENT and shared DUET probe with metadata faults."""
import subprocess,tempfile,unittest
from pathlib import Path
from test_six_plugins import ROOT,PREFIX
COMMON=PREFIX+r'''
static int fault,confirms,sets,renames,queries;
static int error_file(FILE* f){return fault==1||ferror(f);}
#define ferror error_file
#define ENTRY_SNAPSHOT snapshot
#include "src/a2fc_plugin.h"
static struct Entry snapshot[140];
'''
FIX=COMMON+r'''
#include "src/plugins/fixtypes.c"
#undef ferror
static struct Info disk;
static unsigned char mock(unsigned char cmd,void* p){
 struct Info* q=p;
 if(cmd==0xC4){
  ++queries;
  if(q->path==dest)return fault==9?0:fault==10?0x27:0x46;
  if(fault==4 || (fault==5&&queries==2))return 0x27;
  if(fault==6&&queries==2)disk.aux++;
  {unsigned char* path=q->path;*q=disk;q->path=path;}return 0;
 }
 if(cmd==0xC3){++sets;if(!confirms)abort();if(fault==7)return 0x27;disk=*q;return 0;}
 if(cmd==0xC2){++renames;return fault==11?0x27:0;}
 abort();
}
static unsigned char consent(const char* q){++confirms;return fault!=3;}
static unsigned char fullpath(char* p,const struct Panel* pan,const struct Entry* e){strcpy(p,pan->path);return 1;}
static int close_file(FILE* f){int r=fclose(f);return fault==2?-1:r;}
int main(int argc,char**argv){
 struct A2fcApi api={0};struct Panel panels[2]={0};unsigned char active=0,buf[512];char note[80],reselect[17];
 fault=atoi(argv[3]);strcpy(snapshot[0].name,argv[2]);snapshot[0].type=6;panels[0].count=1;strcpy(panels[0].path,argv[1]);
 disk.type=6;disk.aux=0x1234;disk.access=fault==8?0xE1:0xE3;disk.storage=1;disk.blocks=2;disk.mdate=123;disk.ctime=42;
 api.version=5;api.panels=panels;api.active=&active;api.selected=snapshot;api.copy_buf=buf;api.note=note;api.reselect=reselect;
 api.mli=mock;api.build_full=fullpath;api.confirm=consent;api.fopen=fopen;api.fread=fread;api.fclose=close_file;
 api.strlen=strlen;api.strcmp=strcmp;api.strcpy=strcpy;api.sprintf=sprintf;api.memcpy=memcpy;
 plugin_entry(&api);
 printf("%u %u %u %u %u %d %d %d %s\n",disk.type,disk.aux,disk.access,disk.mdate,disk.ctime,sets,renames,confirms,note);return 0;
}
'''
IDENT=COMMON+r'''
#include "src/plugins/ident.c"
#undef ferror
static int close_file(FILE* f){int r=fclose(f);return fault==2?-1:r;}
static int seek_file(FILE* f,long p,int how){return fault==3?-1:fseek(f,p,how);}
int main(int argc,char** argv){
 struct A2fcApi api={0};struct Panel panels[2]={0};struct Entry ent={0};unsigned char active=0,buf[512];char note[80],reselect[17];
 fault=atoi(argv[5]);strcpy(ent.name,argv[2]);ent.type=atoi(argv[3]);ent.aux=atoi(argv[4]);
 {FILE* f=fopen(argv[1],"rb");fseek(f,0,SEEK_END);ent.size=ftell(f);fclose(f);}
 strcpy(panels[0].path,"/FIXTURE");api.panels=panels;api.active=&active;api.selected=&ent;api.full=argv[1];api.copy_buf=buf;api.note=note;api.reselect=reselect;
 api.fopen=fopen;api.fread=fread;api.fclose=close_file;api.fseek=seek_file;api.strcpy=strcpy;api.sprintf=sprintf;api.memset=memset;
 plugin_entry(&api);puts(note);return 0;
}
'''
# cc65's two-word view of a 32-bit size is emulated without host long/word widths.
IDENT=IDENT.replace('#include "src/plugins/ident.c"',(ROOT/'src/plugins/ident.c').read_text().replace('"../a2fc_plugin.h"','"src/a2fc_plugin.h"').replace('"../duet_probe.h"','"src/duet_probe.h"').replace('unsigned long l; unsigned int w[2]','uint32_t l; uint16_t w[2]'))
IDENT='#include <stdint.h>\n'+IDENT
SONG=bytes([12,100,152,1,1,2,12,90,140,8,80,130,12,70,120,0,255,12])
class Formats(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='formats-',dir='/tmp');cls.root=Path(cls.tmp.name);cls.exes={}
  for name,c in [('fix',FIX),('ident',IDENT)]:
   p=cls.root/(name+'.c');p.write_text(c);exe=cls.root/name
   r=subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-Wno-incompatible-function-pointer-types','-fsanitize=address,undefined','-I',str(ROOT),str(p),'-o',str(exe)],capture_output=True,text=True)
   if r.returncode:raise RuntimeError(r.stderr)
   cls.exes[name]=exe
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def call(self,tool,data=SONG,name='M.SONG',fault=0,typ=6,aux=0):
  p=self.root/'input';p.write_bytes(data)
  args=[str(self.exes[tool]),str(p),name]+([str(fault)] if tool=='fix' else [str(typ),str(aux),str(fault)])
  out=subprocess.check_output(args,text=True);self.assertEqual(p.read_bytes(),data);return out
 def test_duet_repair_preserves_name_contents_dates_access(self):
  for padding in (b'',bytes(234),bytes(range(255))):
   out=self.call('fix',SONG+padding);self.assertTrue(out.startswith('213 53479 227 123 42 1 0 1 '),out)
 def test_duet_failures_never_write_metadata(self):
  for fault in (1,2,3,4,5,6,7,8):
   out=self.call('fix',fault=fault).split();self.assertEqual(out[0],'6');self.assertEqual(out[6],'0');self.assertEqual(out[5],str(int(fault==7)))
 def test_malformed_candidates_never_repair(self):
  for data in (b'',b'MB1'+bytes(100),SONG[:-1],SONG+bytes(256),bytes([12,1,2])*4,bytes([1,9,1])+SONG,bytes(7169)):
   out=self.call('fix',data);self.assertEqual(out.split()[5:8],['0','0','0'],out)
 def test_suffix_confirmation_collision_and_lookup_errors(self):
  for fault in (0,3,9,10,11):
   out=self.call('fix',b'hello',name='HELLO.TXT',fault=fault).split()
   self.assertEqual(out[5],str(int(fault!=3)));self.assertEqual(out[6],str(int(fault in (0,11))))
   if fault!=3:self.assertEqual(out[:5],['4','0','227','123','42'])
 def test_bin_suffix_keeps_dos_address(self):
  out=self.call('fix',b'hello',name='HELLO.BIN');self.assertTrue(out.startswith('6 4660 '));self.assertEqual(out.split()[5],'0')
 def test_ident_duet_and_invalid_candidates(self):
  self.assertIn('Electric Duet compatible',self.call('ident'))
  self.assertIn('Invalid/unrecognized',self.call('ident',SONG[:-1]))
  for fault in (1,2,3):self.assertIn('error',self.call('ident',fault=fault))
 def test_ident_supported_format_families(self):
  cases=[('FONT',7,0,b'x','font'),('A.FOTO1',6,0,b'x','Purplesoft'),('A',8,0x8066,b'x','LZ4FH'),('A',6,0x5800,bytes(572),'Print Shop'),('A',6,0x400,bytes(1024),'Lo-res'),('A',6,0,b'DGR','DGR pixmap'),('A.PT3',6,0,b'x','PT3'),('A',6,0,b'ProTracker 3.7','PT3'),('A.MD',4,0,b'hello','Markdown'),('A',8,0x4001,bytes(8192),'Packed double'),('A',6,0xE001,bytes(8192),'816/Paint'),('A',0xF2,0,bytes(8192),'Extasie'),('A',8,0x2000,bytes(16384),'DHGR'),('A',6,0,b'MB1','Mockingboard'),('A.NIB',6,0,bytes(232960),'nibble'),('A.HDV',6,0,bytes(1028)+b'\xF1'+bytes(1019),'ProDOS block')]
  for name,typ,aux,data,label in cases:
   with self.subTest(name=name,typ=typ,aux=aux):self.assertIn(label,self.call('ident',data,name,typ=typ,aux=aux))
if __name__=='__main__':unittest.main()
