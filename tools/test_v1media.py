"""Real C media readers: bounded AUX, consent, complete reads and both CPUs."""
import hashlib,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_pfswrite import ROOT
CORPUS=Path(os.environ.get('A2FC_V1_CORPUS','/tmp/a2fc-v1-corpus'))
H=r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef strcpy
#undef memcpy
struct A2fcApi;
static int fault,reads,opens,closes,ioerr,consents;
static unsigned int frames,writes;
static unsigned char aux[16384];
static const char* source_path;
static int ferr(FILE* f){return ioerr || ferror(f);}
#define ferror ferr
#include MEDIA_SOURCE
#undef ferror
#ifdef GRAPHICS
void vg_write(unsigned char c){if(vg_addr<0x4000 || vg_addr>=0x8000)abort();aux[vg_addr-0x4000]=c;++writes;}
void vg_read(void){if(vg_addr<0x4000 || vg_addr+vg_count>0x8000)abort();memcpy(vg_buf,aux+vg_addr-0x4000,vg_count);}
void plugin_entry(const struct A2fcApi* a){(void)a;}
#else
void mv_host_display(const unsigned char* p){unsigned int i,sum=0;++frames;for(i=0;i<1920;++i){if(p[i]>15)abort();sum=(sum*31+p[i])&65535;}printf("frame %u %u\n",frames,sum);}
#endif
static unsigned char consent(void){++consents;return fault!=8;}
static char key(void){return frames<2?32:27;}
static void clear(void){}
static FILE* opn(const char* p,const char* m){++opens;ioerr=0;if(strcmp(m,"rb"))abort();if(fault==1 || (fault==7 && opens==2))return NULL;return fopen(p,m);}
static size_t rd(void* p,size_t z,size_t n,FILE* f){++reads;if((fault==2 && reads==2)||(fault==5 && opens==2)||(fault==6 && reads==5)){ioerr=1;return 0;}return fread(p,z,n,f);}
static int close_(FILE* f){++closes;return fclose(f) || fault==3 || (fault==4 && closes==2)?EOF:0;}
static int seek_(FILE* f,long at,int mode){
 if(fault==9)return -1;
#ifdef __CC65__
 {unsigned char buf[64];FILE* again;unsigned int n;if(mode!=SEEK_SET || at<0 || fclose(f))return -1;again=fopen(source_path,"rb");if(again!=f)return -1;while(at){n=at>64?64:(unsigned int)at;if(fread(buf,1,n,f)!=n)return -1;at-=n;}return 0;}
#else
 return fseek(f,at,mode);
#endif
}
int main(int argc,char**argv){
 struct A2fcApi api;struct Entry e;char note[80],reselect[80];unsigned char flags=0;unsigned int i;
 memset(&api,0,sizeof api);memset(&e,0,sizeof e);memset(note,0,sizeof note);memset(aux,0xA5,sizeof aux);
 source_path=argv[1];fault=atoi(argv[2]);e.type=6;e.size=1;strcpy(e.name,"SAMPLE");
 api.full=(char*)source_path;if(fault==10)api.full="/RAM/PICTURE";api.selected=&e;api.note=note;api.reselect=reselect;api.fopen=opn;api.fread=rd;api.fclose=close_;api.fseek=seek_;api.strcpy=strcpy;api.aux_consent=consent;api.wait_key=key;api.clrscr=clear;
#ifdef GRAPHICS
 flags=vg_run(&api);if(flags&4)fwrite(aux,1,16384,stdout);
#endif
#ifndef GRAPHICS
 plugin_entry(&api);for(i=0;i<16384;++i)if(aux[i]!=0xA5)abort();
#endif
 fprintf(stderr,"%u %u %d %d %d %s\n",flags,writes,opens,closes,consents,note);return 0;
}
'''
def pcs():
 # Independent square and a complete zero bitmap, not copied from PCS.
 obj=bytes([1,14,4,10,20,20,10,10,10,20,20])
 return bytes(28)+bytes([1,len(obj)])+obj+b'\x01\x00'*32+b'\x01\x01'
def movie():
 def cmd(t,p=b''):return bytes([t])+len(p).to_bytes(2,'little')+p
 return cmd(1,bytes([0,0,10,10])+bytes(252))+cmd(2,b'\x00\x00'+b'\xff'*8192)+cmd(3,b'\x00\x00'+bytes(8192))+cmd(6)+cmd(5,b'\x01\x01\0\0\x30\xC0')+cmd(0)+cmd(7)
class Media(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='v1media-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.exes={}
  for name in ('dgmagi','pcsvw','mvmovie'):
   exe=cls.p/name;defines=['-DMEDIA_SOURCE="src/plugins/'+name+'.c"']+([] if name=='mvmovie' else ['-DGRAPHICS'])
   subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),*defines,str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True);cls.exes[name]=exe
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_file(self,name,d,fault=0,exe=None):
  src=self.p/'source';src.write_bytes(d)
  r=subprocess.run(([str(self.exes[name])] if exe is None else exe)+[str(src),str(fault)],check=True,capture_output=True,timeout=60)
  self.assertEqual(src.read_bytes(),d);status=r.stderr.decode().strip().split(' ',5);status[1]=str(int(status[1])&65535);return r.stdout,status
 def test_valid_and_bounds(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   out,st=self.run_file(name,d);self.assertEqual(st[2:4],['2','2']);self.assertEqual(st[4],'0' if name=='mvmovie' else '1');self.assertTrue(out)
   if name=='dgmagi':self.assertEqual(len(out),16384)
 def test_validation_before_consent(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   for bad in (b'',d[:-1],d+b'\xFF'*5):
    out,st=self.run_file(name,bad);self.assertFalse(out);self.assertEqual(st[0:2],['0','0']);self.assertEqual(st[4],'0');self.assertTrue(st[5])
   for fault in ((1,2,3,6) if name!='pcsvw' else (1,3)):
    # Short .DPC needs only two reads, so faults at later reads cannot fire.
    src=d if name!='dgmagi' else b'\x80\0\0\xA0\0\0\0'+bytes(2048)
    out,st=self.run_file(name,src,fault);self.assertFalse(out);self.assertEqual(st[1],'0');self.assertEqual(st[4],'0');self.assertIn('error',st[5])
 def test_refusal_reopen_read_close_seek(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   if name!='mvmovie':
    out,st=self.run_file(name,d,10);self.assertFalse(out);self.assertEqual(st[:5],['0','0','0','0','0'])
    out,st=self.run_file(name,d,8);self.assertFalse(out);self.assertEqual(st[:2],['0','0']);self.assertEqual(st[2:5],['1','1','1'])
   for fault in (4,5,7):
    out,st=self.run_file(name,d,fault);self.assertTrue(st[5]);self.assertIn('error',st[5])
    if name!='mvmovie':self.assertEqual(st[0],'1');self.assertFalse(out)
   if name!='dgmagi':self.assertIn('error',self.run_file(name,d,9)[1][5])
 def test_embedded_movie_code_is_refused(self):
  d=movie();at=3+256+3+8194+3+8194
  bad=d[:at]+b'\x04\x01\x00\x60'+d[at:]
  out,st=self.run_file('mvmovie',bad);self.assertFalse(out);self.assertIn('Unsupported',st[5]);self.assertEqual(st[2:4],['1','1'])
 def test_local_originals_and_dgmagi_oracle(self):
  if not (CORPUS/'pal-original.raw').exists():self.skipTest('local original corpus not installed')
  for p in CORPUS.glob('*.PB.raw'):
   original=p.name[:-4]+'#064000';d=(CORPUS/'extracted'/original).read_bytes();out,st=self.run_file('pcsvw',d);self.assertEqual(out[:8192],p.read_bytes()[:8192]);self.assertEqual(st[0],'5')
  d=(CORPUS/'pal-no-text.dpc').read_bytes();out,st=self.run_file('dgmagi',d);self.assertEqual(st[0],'7');self.assertEqual(out,(CORPUS/'pal-original.raw').read_bytes())
  cache=Path.home()/'.cache/a2fc/moviemaker/out';seen=set()
  for p in cache.rglob('*'):
   if p.is_file() and p.name.endswith('.MVM.bin'):
    d=p.read_bytes();digest=hashlib.sha256(d).hexdigest()
    if digest in seen:continue
    if d[:3]!=b'\x01\x00\x01':continue
    seen.add(digest);out,st=self.run_file('mvmovie',d);self.assertTrue(out,p.name);self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  self.assertEqual(len(seen),13)
 def test_both_cpus_real_decoder(self):
  if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
  path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
  samples={'dgmagi':[b'\x80\0\0\xA0\0\0\0'],'pcsvw':[pcs()],'mvmovie':[movie()]}
  if CORPUS.exists():samples['pcsvw'] += [p.read_bytes() for p in (CORPUS/'extracted').glob('*.PB#064000')]
  if (CORPUS/'pal-no-text.dpc').exists():samples['dgmagi'].append((CORPUS/'pal-no-text.dpc').read_bytes())
  for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
   cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
   for name,ds in samples.items():
    exe=self.p/(name+target);defines=['-DMEDIA_SOURCE="src/plugins/'+name+'.c"']+([] if name=='mvmovie' else ['-DGRAPHICS'])
    subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),*defines,'-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
    for d in ds:self.assertEqual(self.run_file(name,d),self.run_file(name,d,exe=['sim65',str(exe)]))
if __name__=='__main__':unittest.main()
