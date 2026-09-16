"""Execute both image phases and the shared DOS engine on disposable files."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from mini33_fixture import make_disk as _make_disk, read_files


def make_disk(files):
    # the sector offsets below assume the fixture's original ascending
    # layout (T3 S0 list, S1 data)
    return _make_disk(files, descending=False)
ROOT = Path(__file__).resolve().parents[1]
C = r'''
#define __fastcall__
#include "src/a2fc_plugin.h"
#include <string.h>
#include <stddef.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
void prep(const struct A2fcApi*);
void put(const struct A2fcApi*);
static struct A2fcApi api;
static struct Panel panels[2];
static struct Entry selected;
static unsigned char active,buf[512];
static char full[81],other_full[81],input[17],note[100],reselect[64];
static int mode,at,reads,writes,closes,seeks,renames,phase;
static FILE* error_file;
static FILE* original_read;
static int damaged;
int image_error(FILE* f){return f==error_file || ferror(f);}
struct Info {unsigned char n;unsigned char* path;unsigned char access,type;unsigned int aux;unsigned char storage;unsigned int blocks,md,mt,cd,ct;};
struct Rename {unsigned char n;unsigned char *old,*newpath;};
static int ends(const char* p,const char* s){size_t n=strlen(p),m=strlen(s);return n>=m && !strcmp(p+n-m,s);}
static void path(char* out,unsigned char* p){memcpy(out,p+1,p[0]);out[p[0]]=0;}
static unsigned char mli(unsigned char cmd,void* p){
 struct Info* i=p;char name[81],to[81];FILE* f;int fd;
 if(cmd==0xC2){struct Rename* r=p;path(name,r->old);path(to,r->newpath);++renames;
  if((mode==6 && renames==at) || (mode==7 && renames>=2))return 0x27;
  if(!access(to,F_OK))return 0x47;return rename(name,to)?0x27:0;}
 path(name,i->path);
 if(cmd==0xC0){if(mode==8)return 0x48;fd=open(name,O_CREAT|O_EXCL|O_WRONLY,0600);if(fd<0)return 0x47;return close(fd)?0x27:0;}
 if(cmd!=0xC4)abort();
 if(mode==9)return 0x27;
 /* mode 17: A2FC.BAK appears during the copy, so the install pre-check refuses. */
 if(mode==17 && phase==3 && ends(name,"A2FC.BAK")){unsigned char* q=(unsigned char*)p+offsetof(struct Info,access);memset(q,0,15);q[0]=0xC3;q[4]=1;return 0;}
 f=fopen(name,"rb");if(!f)return 0x46;fclose(f);
 /* replace_info returns packed 15 bytes rather than a native Info. */
 if(ends(name,"A2FC.BAK") || phase==3){unsigned char* q=(unsigned char*)p+offsetof(struct Info,access);memset(q,0,15);q[0]=0xC3;q[4]=1;}
 else {i->access=mode==10?1:0xC3;i->storage=1;i->aux=0x2000;i->type=6;}
 return 0;
}
static FILE* op(const char* p,const char* m){
 if(mode==13 && phase==3 && !strcmp(p,panels[1].path))return NULL;
 if(strchr(m,'w') && !ends(p,"A2FC.DOS"))abort();
 {FILE* f=fopen(p,m);if(phase==2 && !strcmp(p,panels[1].path))original_read=f;return f;}
}
static size_t rd(void* p,size_t s,size_t n,FILE* f){++reads;if((mode==1 && reads==at) || (mode==16 && phase==2 && f==original_read && ftell(f)>=at)){error_file=f;return 0;}return fread(p,s,n,f);}
static size_t wr(const void* p,size_t s,size_t n,FILE* f){++writes;if(mode==2 && writes==at){error_file=f;fwrite(p,s,n/2,f);return n/2;}{
 size_t got=fwrite(p,s,n,f);
 if(mode==14 && phase==2 && !damaged){long mark=ftell(f);int value;damaged=1;
  fseek(f,at,SEEK_SET);value=fgetc(f);fseek(f,at,SEEK_SET);fputc(value^1,f);fseek(f,mark,SEEK_SET);}
 return got;
}}
static int cl(FILE* f){int r=fclose(f);++closes;return mode==3 && closes==at?-1:r;}
static int sk(FILE* f,long at_,int w){++seeks;if(mode==4 && seeks==at)return -1;return fseek(f,at_,w);}
static int rm(const char* p){if(mode==5)return -1;return remove(p);}
static unsigned char cf(const char* p){
 if(mode==15){FILE* changed=fopen(panels[1].path,"r+b");fseek(changed,at,SEEK_SET);fputc(0x80,changed);fclose(changed);}
 return mode!=11;
}
static void progress(const char* p,unsigned long n,unsigned long t){}
int main(int argc,char**argv){
 mode=atoi(argv[1]);at=atoi(argv[2]);strcpy(full,argv[3]);strcpy(panels[1].path,argv[4]);
 panels[1].fs=FS_DOS33;panels[1].img_len=strlen(argv[4]);strcpy(selected.name,"NEW");selected.type=6;
 api.panels=panels;api.active=&active;api.full=full;api.other_full=other_full;api.input=input;
 api.copy_buf=buf;api.note=note;api.reselect=reselect;api.selected=&selected;
 api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;api.strcmp=strcmp;api.strlen=strlen;api.sprintf=sprintf;
 api.mli=mli;api.fopen=op;api.fread=rd;api.fwrite=wr;api.fclose=cl;api.fseek=sk;api.remove=rm;
 api.confirm=cf;api.progress_bar=progress;
 phase=1;api.arg='P';prep(&api);
 if(input[0]=='I'){
  /* The loader borrows other_full and rereads panels between phases. */
  strcpy(other_full,"/LOADER/DOSPUT.PLG");phase=2;api.arg='I';put(&api);
  if(mode==12){FILE* changed=fopen(panels[1].path,"r+b");fputc(0x99,changed);fclose(changed);}
  strcpy(other_full,"/LOADER/DOSIMAGE.PLG");phase=3;api.arg=input[0]=='F'?'F':'X';prep(&api);
 }
 printf("%d %d %d %d %d %s\n",reads,writes,closes,seeks,renames,note);return 0;
}
'''
class DosImage(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.build=tempfile.TemporaryDirectory(prefix='dim-build-',dir='/tmp');p=Path(cls.build.name)
  (p/'h.c').write_text(C);objs=[]
  for stem,entry in [('dosimage','prep'),('dosput','put')]:
   obj=p/(stem+'.o');objs.append(str(obj))
   subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-D_FORTIFY_SOURCE=0','-DPLUGIN_HOST','-D__fastcall__=',
    '-Dferror=image_error','-Dplugin_entry='+entry,'-D__plugin_header='+stem+'_header','-I',str(ROOT),'-c',str(ROOT/'src/plugins'/f'{stem}.c'),'-o',str(obj)],check=True,capture_output=True)
  cls.exe=p/'test'
  subprocess.run(['cc','-std=c99','-I',str(ROOT),str(p/'h.c'),*objs,'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.build.cleanup()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='dim-',dir='/tmp');self.addCleanup(self.tmp.cleanup)
  self.p=Path(self.tmp.name);self.src=self.p/'NEW';self.disk=self.p/'D.DSK'
  self.original=make_disk([('KEEP',0x80,b'precious\r'*70)])
  self.payload=bytes(range(256))*32;self.src.write_bytes(self.payload);self.disk.write_bytes(self.original)
 def run_op(self,mode=0,at=1):
  out=subprocess.check_output([self.exe,str(mode),str(at),str(self.src),str(self.disk)],text=True)
  self.assertEqual(self.src.read_bytes(),self.payload)
  return [int(x) for x in out.split()[:5]],out
 def assert_original_recoverable(self):
  self.assertTrue(any(p.exists() and p.read_bytes()==self.original for p in (self.disk,self.p/'A2FC.BAK')))
 def test_copy_and_container_bytes(self):
  for suffix in ('DSK','DO','2MG'):
   self.disk=self.p/('D.'+suffix)
   header=bytearray(64)
   if suffix=='2MG':
    header[:4]=b'2IMG';header[8:12]=b'\x40\x00\x01\x00';header[20:24]=(280).to_bytes(4,'little')
    header[24:28]=(64).to_bytes(4,'little');header[28:32]=(143360).to_bytes(4,'little')
   before=(header if suffix=='2MG' else b'')+self.original;self.disk.write_bytes(before)
   _,out=self.run_op();self.assertIn('Copied to DOS 3.3 image',out)
   after=self.disk.read_bytes();base=64 if suffix=='2MG' else 0
   self.assertEqual(after[:base],before[:base]);files=read_files(after[base:])
   self.assertEqual(files['KEEP'],read_files(self.original)['KEEP'])
   expected=b'\x00\x20'+len(self.payload).to_bytes(2,'little')+self.payload
   self.assertEqual(files['NEW']['data'],expected+bytes((-len(expected))%256))
   self.assertFalse((self.p/'A2FC.DOS').exists());self.assertFalse((self.p/'A2FC.BAK').exists())
 def test_every_io_failure_preserves_original(self):
  counts,_=self.run_op();self.disk.write_bytes(self.original)
  # Exercise all writes/closes/renames, and reads/seeks at phase boundaries.
  for mode,count in ((1,counts[0]),(2,counts[1]),(3,counts[2]),(4,counts[3]),(6,counts[4])):
   points=range(1,count+1) if mode in (2,3,6) else sorted(set([1,2,count//2,count-1,count]))
   for at in points:
    with self.subTest(mode=mode,at=at):
     for p in (self.p/'A2FC.DOS',self.p/'A2FC.BAK'):p.unlink(missing_ok=True)
     self.disk.write_bytes(self.original);_,out=self.run_op(mode,at)
     self.assertNotIn('Copied to DOS 3.3 image',out);self.assert_original_recoverable()
 def test_preexisting_names_cancel_protection_and_full(self):
  for name in ('A2FC.DOS','A2FC.BAK'):
   p=self.p/name;p.write_bytes(b'untouched');self.run_op();self.assertEqual(p.read_bytes(),b'untouched');p.unlink()
   self.assertEqual(self.disk.read_bytes(),self.original)
  for mode in (8,9,10,11):
   self.run_op(mode);self.assertEqual(self.disk.read_bytes(),self.original)
 def test_refused_install_removes_its_own_temp_and_says_nothing_changed(self):
  # A2FC.BAK appears while the copy runs: replace_commit's pre-check refuses,
  # nothing was renamed, so the verified A2FC.DOS this run created is dropped.
  _,out=self.run_op(17);self.assertEqual(self.disk.read_bytes(),self.original)
  self.assertIn('nothing changed',out);self.assertNotIn('install failed',out)
  self.assertFalse((self.p/'A2FC.DOS').exists())
 def test_restore_failure_and_retained_backup(self):
  _,out=self.run_op(7);self.assertIn('recovery',out);self.assert_original_recoverable()
  self.assertTrue((self.p/'A2FC.DOS').exists())
 def test_backup_cleanup_failure_keeps_verified_copy_and_original(self):
  _,out=self.run_op(5);self.assertIn('old image retained',out)
  self.assertEqual((self.p/'A2FC.BAK').read_bytes(),self.original)
  self.assertIn('NEW',read_files(self.disk.read_bytes()))
 def container(self):
  header=bytearray(64);header[:4]=b'2IMG';header[8:12]=b'\x40\x00\x01\x00'
  header[20:24]=(280).to_bytes(4,'little');header[24:28]=(64).to_bytes(4,'little');header[28:32]=(143360).to_bytes(4,'little')
  return bytes(header)+self.original
 def test_unrelated_bytes_corrupted_by_a_successful_write(self):
  for base in (0,64):
   self.disk=self.p/('D.2MG' if base else 'D.DSK');before=self.container() if base else self.original
   for at in (0,base+49*256,base+143359):
    with self.subTest(base=base,at=at):
     self.disk.write_bytes(before);_,out=self.run_op(14,at)
     self.assertNotIn('Copied to DOS 3.3 image',out)
     self.assertEqual(self.disk.read_bytes(),before)
 def test_container_changed_during_confirmation(self):
  self.disk=self.p/'D.2MG';before=self.container()
  for at in (0,19,24):
   with self.subTest(at=at):
    self.disk.write_bytes(before);_,out=self.run_op(15,at)
    expected=bytearray(before);expected[at]=0x80
    self.assertNotIn('Copied to DOS 3.3 image',out)
    self.assertEqual(self.disk.read_bytes(),expected)
 def test_preservation_scan_read_errors_and_container_trailer(self):
  self.disk=self.p/'D.2MG';before=self.container()+b'container comment'
  for mode,at in ((16,0),(16,256),(16,143360),(14,len(before)-1)):
   with self.subTest(mode=mode,at=at):
    self.disk.write_bytes(before);_,out=self.run_op(mode,at)
    self.assertNotIn('Copied to DOS 3.3 image',out)
    self.assertEqual(self.disk.read_bytes(),before)
    self.assertFalse((self.p/'A2FC.DOS').exists())
 def test_crc_on_both_native_cpus(self):
  import zlib
  expected=zlib.crc32(bytes(range(256))*3)^0xFFFFFFFF
  code=r'''#define PLUGIN_HOST
#include "src/plugins/dosimage.c"
static unsigned char sample[256];
int main(void) {
 unsigned int i;unsigned char j;
 buf=(unsigned char*)"123456789";image_crc=0xFFFFFFFFUL;image_hash(9);
 if(image_crc!=0x340BC6D9UL)return 1;
 buf=sample;for(i=0;i<256;++i)sample[i]=i;
 image_crc=0xFFFFFFFFUL;for(j=0;j<3;++j)image_hash(256);
 return image_crc!=EXPECTED;
}
'''.replace('EXPECTED',str(expected)+'UL')
  p=Path(self.build.name);(p/'crc.c').write_text(code)
  for cpu in ('sim6502','sim65c02'):
   exe=p/('crc-'+cpu)
   subprocess.run(['cl65','-t',cpu,'-O','-I',str(ROOT),str(p/'crc.c'),'-o',str(exe)],check=True,capture_output=True)
   subprocess.run(['sim65',str(exe)],check=True)
 def test_full_dos_image_and_invalid_or_locked_2mg(self):
  disk=bytearray(self.original);vtoc=17*4096;disk[vtoc+0x38:vtoc+256]=bytes(256-0x38)
  self.disk.write_bytes(disk);_,out=self.run_op();self.assertIn('DOS image full',out)
  self.assertEqual(self.disk.read_bytes(),disk)
  header=bytearray(64);header[:4]=b'2IMG';header[8:12]=b'\x40\x00\x01\x00'
  header[20:24]=(280).to_bytes(4,'little');header[24:28]=(64).to_bytes(4,'little');header[28:32]=(143360).to_bytes(4,'little')
  self.disk=self.p/'D.2MG'
  for offset,value in ((19,0x80),(12,1),(12,2),(8,63),(24,32),(27,1),(28,1)):
   bad=bytearray(header);bad[offset]=value;before=bad+self.original
   self.disk.write_bytes(before);_,out=self.run_op();self.assertNotIn('Copied to DOS',out)
   self.assertEqual(self.disk.read_bytes(),before);self.assertFalse((self.p/'A2FC.DOS').exists())
 def test_original_changed_or_unreadable_before_install(self):
  for mode in (12,13):
   self.disk.write_bytes(self.original);(self.p/'A2FC.DOS').unlink(missing_ok=True)
   _,out=self.run_op(mode);self.assertIn('A2FC.DOS retained',out)
   expected=(b'\x99'+self.original[1:]) if mode==12 else self.original
   self.assertEqual(self.disk.read_bytes(),expected)
   self.assertIn('NEW',read_files((self.p/'A2FC.DOS').read_bytes()))
 def test_shipped_demo_is_writable(self):
  from mkdos33 import build
  self.disk.write_bytes(build([('KEEP',0x80,b'original')]))
  _,out=self.run_op();self.assertIn('Copied to DOS 3.3 image',out)
  self.assertIn('NEW',read_files(self.disk.read_bytes()))
 def test_malformed_catalog_end_and_ts_offsets_preserve_image(self):
  before=make_disk([('KEEP',0x80,b'K'*32000)])
  for at,value in ((48*256+5,1),(49*256+5,0),((17*16+1)*256+1,17)):
   with self.subTest(at=at):
    bad=bytearray(before);bad[at]=value;self.disk.write_bytes(bad)
    _,out=self.run_op()
    self.assertNotIn('Copied to DOS',out)
    self.assertEqual(self.disk.read_bytes(),bad)
    self.assertFalse((self.p/'A2FC.DOS').exists())
 def test_collision_and_malformed_image(self):
  for disk in (make_disk([('NEW',0,b'old')]),self.original[:-1],self.original+b'extra'):
   self.disk.write_bytes(disk);self.run_op();self.assertEqual(self.disk.read_bytes(),disk)
   self.assertFalse((self.p/'A2FC.DOS').exists())
if __name__=='__main__':unittest.main()
