"""Execute the shipped DOSWRITE C against disposable DOS disks and I/O faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from mini33_fixture import make_disk as _make_disk, read_files, offset


def make_disk(files):
    # the sector offsets below (T3 S0 list, S1 data) assume the fixture's
    # original ascending layout
    return _make_disk(files, descending=False)
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
static int injected_error(FILE*);
#define ferror injected_error
#include "src/plugins/doswrite.c"
#undef ferror
static FILE *disk,*input;
static struct Panel panels[2];
static struct Entry selected;
static unsigned char scratch[512],active;
static char path[64],note_text[100],reselect[64];
static int mode,reads,writes,opens,closes,fail_at;
static unsigned char target_unit=0xE0;
static unsigned char dos_order[16]={0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15};
static int injected_error(FILE* f){return (mode==9 && opens==2) || ferror(f);}
void dw_mainbank(void){}
unsigned char dw_protected(unsigned char u){return mode==1?0x80:mode==21?1:0;}
static unsigned char mli(unsigned char cmd,void* p) {
 struct Block* b=p;unsigned int h;unsigned char* q;
 if(cmd==0xC5){struct Online* o=p;if(mode==15)return 0x27;memset(o->buffer,0,256);o->buffer[0]=0x71; o->buffer[1]='V';return 0;}
 if(cmd==0xC4){struct Info* i=p;i->storage=1;i->access=0xC3;i->aux=0x2000;i->type=selected.type;return mode==12?0x27:0;}
 if(b->unit!=target_unit || b->block>=280 || (cmd!=0x80 && cmd!=0x81))abort();
 if(cmd==0x80){++reads;if(mode==2 && reads==fail_at)return 0x27;}
 else {++writes;if(mode==3 && writes==fail_at)return 0x27;}
 for(h=0;h<2;++h){
  long at=((long)(b->block/8)*16+dos_order[(b->block%8)*2+h])*256;
  fseek(disk,at,SEEK_SET);q=b->buffer+h*256;
  if(cmd==0x80){if(fread(q,1,256,disk)!=256)abort();}
  else {
   if(mode==4 && writes==fail_at){if(!h)fwrite(q,1,128,disk);fflush(disk);return 0x27;}
   if(fwrite(q,1,256,disk)!=256)abort();
  }
 }
 if(cmd==0x81){fflush(disk);if(mode==5 && writes==fail_at){long at=((long)(b->block/8)*16+dos_order[(b->block%8)*2])*256;
 fseek(disk,at,SEEK_SET);h=fgetc(disk);fseek(disk,at,SEEK_SET);fputc(h^1,disk);fflush(disk);}}
 return 0;
}
static FILE* source_open(const char* p,const char* m){++opens;if(mode==7 && opens==2)return NULL;input=fopen(path,"rb");return input;}
static size_t source_read(void* p,size_t s,size_t n,FILE* f){
 if(mode==8 && opens==2)return 0;
 {size_t got=fread(p,s,n,f);if(mode==18 && opens==3 && got)((unsigned char*)p)[0]^=1;return got;}
}
static int source_close(FILE* f){++closes;fclose(f);return ((mode==10 && closes==3) || (mode==17 && closes==1))?-1:0;}
static unsigned char confirm(const char* s){return mode!=6;}
static void progress(const char* s,unsigned long n,unsigned long t){if(mode==11)cancelled=1;}
int main(int argc,char**argv){
 struct A2fcApi api;memset(&api,0,sizeof api);
 disk=fopen(argv[1],"r+b");strcpy(path,argv[2]);mode=atoi(argv[3]);fail_at=atoi(argv[4]);
 strcpy(selected.name,"NEW");selected.type=atoi(argv[5]);
 strcpy(panels[0].path,"/V");panels[1].fs=FS_DOS33;panels[1].dir_key=target_unit=(argc>6?atoi(argv[6]):0xE0);
 api.panels=panels;api.active=&active;api.selected=&selected;api.full="/V/NEW";api.copy_buf=scratch;
 api.note=note_text;api.reselect=reselect;api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;
 api.strlen=strlen;api.sprintf=sprintf;api.mli=mli;api.fopen=source_open;api.fread=source_read;api.fclose=source_close;
 api.confirm=confirm;api.progress_bar=progress;
 if(mode==19)api.arg=1;
 if(mode==20)panels[1].img_len=5;
 plugin_entry(&api);fclose(disk);
 printf("%d %d %s\n",writes,reads,note_text);return 0;
}
'''
class DosWrite(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='dw-build-',dir='/tmp');p=Path(cls.tmp.name)
  (p/'test.c').write_text(C);cls.exe=p/'test'
  subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
  self.tmpcase=tempfile.TemporaryDirectory(prefix='dw-',dir='/tmp');self.addCleanup(self.tmpcase.cleanup)
  self.p=Path(self.tmpcase.name);self.disk=self.p/'disk.do';self.src=self.p/'SRC'
  self.original=make_disk([('KEEP',0x80,b'original\r'*100)])
  self.disk.write_bytes(self.original);self.payload=bytes(range(256))*4+b'end';self.src.write_bytes(self.payload)
 def run_op(self,mode=0,at=1,kind=6):
  out=subprocess.check_output([self.exe,self.disk,self.src,str(mode),str(at),str(kind)],text=True)
  self.assertEqual(self.src.read_bytes(),self.payload)
  return int(out.split()[0]),out
 def assert_keep(self):
  before=read_files(self.original)['KEEP'];after=read_files(self.disk.read_bytes())['KEEP']
  self.assertEqual(after,before)
 def test_types_and_size_boundaries(self):
  for kind,prefix in ((4,b''),(6,b'\x00\x20'),(0xFC,b''),(0xFA,b'')):
   for size in (0,1,252,254,256,512,31232,65535):
    with self.subTest(kind=kind,size=size):
     self.disk.write_bytes(self.original);self.payload=bytes([65])*size;self.src.write_bytes(self.payload)
     _,out=self.run_op(kind=kind);self.assertIn('Copied to DOS',out)
     files=read_files(self.disk.read_bytes());self.assert_keep()
     expected=(prefix+size.to_bytes(2,'little') if kind!=4 else b'')+self.payload
     self.assertEqual(files['NEW']['data'],expected+bytes((-len(expected))%256))
 def test_native_slot_sensor(self):
  code=r'''#include <stdio.h>
unsigned char __fastcall__ dw_protected(unsigned char);
int main(void) {
 unsigned char slot,drive,wp,bad;unsigned char* rom;unsigned char* io;
 unsigned char sig[8]={0xA2,0x20,0xA0,0,0xA2,3,0x86,0x3C};
 unsigned char offsets[5]={0,1,3,5,255};unsigned int i;
 for(slot=1;slot<8;++slot) {
  rom=(unsigned char*)(0xC000U+slot*256U);io=(unsigned char*)(0xC080U+slot*16U);
  for(i=0;i<8;++i)rom[i]=sig[i];rom[255]=0;
  for(drive=0;drive<2;++drive)for(wp=0;wp<2;++wp) {
   io[14]=wp?0x80:0;
   if(dw_protected(slot*16+(drive?0x80:0))!=io[14])return 1;
  }
  for(bad=0;bad<5;++bad) {
   i=offsets[bad];rom[i]^=1;
   if(dw_protected(slot*16)!=1)return 2;
   rom[i]^=1;
  }
  /* Generic ProDOS block ROM signature must never reach Disk II I/O. */
  rom[0]=0x4C;rom[255]=0xEB;
  if(dw_protected(slot*16)!=1)return 3;
 }
 puts("slots OK");return 0;
}
'''
  p=Path(self.tmp.name);(p/'sensor.c').write_text(code)
  # doswrite.s is one .include: the sensing itself is shared with DOS33W.
  (p/'sensor_io.s').write_text((ROOT/'src/plugins/doswrite.s').read_text())
  (p/'dos33_sense.inc').write_text((ROOT/'src/plugins/dos33_sense.inc').read_text())
  for cpu in ('sim6502','sim65c02'):
   exe=p/('sensor-'+cpu)
   subprocess.run(['cl65','-t',cpu,'-O',str(p/'sensor.c'),str(p/'sensor_io.s'),'-o',str(exe)],check=True,capture_output=True)
   self.assertIn('slots OK',subprocess.check_output(['sim65',str(exe)],text=True))
 def test_all_slots_and_drives(self):
  for slot in range(1,8):
   for drive in (0,0x80):
    unit=slot*16+drive
    self.disk.write_bytes(self.original)
    out=subprocess.check_output([self.exe,self.disk,self.src,'0','1','6',str(unit)],text=True)
    if unit==0x70:
     self.assertEqual(self.disk.read_bytes(),self.original)
     self.assertIn('Cannot identify',out)
    else:
     self.assertIn('Copied to DOS',out);self.assert_keep()
 def test_native_16bit_engines(self):
  # sim65 has no lseek: keep the 140 KB disk in Python, replacing only block
  # transport. The same plugin_entry and source stdio run on both real CPUs.
  p=Path(self.tmp.name)
  start=C.index(' if(b->unit!=target_unit')
  end=C.index('static FILE* source_open',start)
  code=C[:start]+r''' if(b->unit!=target_unit || b->block>=280){fprintf(stderr,"BAD block %u unit %u\n",b->block,b->unit);abort();}
 if(cmd==0x80)++reads;else ++writes;
 putchar(cmd);putchar(b->block&255);putchar(b->block>>8);
 if(cmd==0x81)fwrite(b->buffer,1,512,stdout);
 fflush(stdout);
 if(getchar())return 0x27;
 if(cmd==0x80 && fread(b->buffer,1,512,stdin)!=512)abort();
 return 0;
}
'''+C[end:]
  code=code.replace('printf("%d %d %s\\n",writes,reads,note_text);',
                    'putchar(0);printf("%d %d %s\\n",writes,reads,note_text);')
  (p/'sim.c').write_text(code)
  for cpu in ('sim6502','sim65c02'):
   exe=p/cpu
   result=subprocess.run(['cl65','-t',cpu,'-O','-I',str(ROOT),str(p/'sim.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   for size,bad in ((0,None),(31232,None),(65535,None),(1,-1),
                    (1,48*256+5),(1,49*256+5),(1,offset(17,1)+1)):
    with self.subTest(cpu=cpu,size=size,bad=bad):
     disk=bytearray(self.original if bad is None else make_disk([('KEEP',0x80,b'K'*32000)]))
     malformed=bad is not None and bad>=0
     if malformed:disk[bad]=17 if bad==offset(17,1)+1 else 0 if bad==49*256+5 else 1
     before=bytes(disk);self.payload=b'B'*size;self.src.write_bytes(self.payload)
     proc=subprocess.Popen(['sim65',str(exe),str(self.disk),str(self.src),'0','1','6'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
     try:
      while True:
       raw=proc.stdout.read(1);self.assertTrue(raw,'simulator stopped')
       if raw==b'\x00':break
       cmd=raw[0];self.assertIn(cmd,(0x80,0x81))
       block=int.from_bytes(proc.stdout.read(2),'little')
       halves=[(block//8)*4096+(0 if x==0 else 15 if x==15 else 15-x)*256 for x in (block%8*2,block%8*2+1)]
       if cmd==0x81:
        data=proc.stdout.read(512);self.assertEqual(len(data),512)
        for h,at in enumerate(halves):disk[at:at+256]=data[h*256:(h+1)*256]
        proc.stdin.write(b'\x00')
       else:proc.stdin.write(b'\x00'+b''.join(disk[at:at+256] for at in halves))
       proc.stdin.flush()
      out=proc.stdout.readline().decode();proc.wait(timeout=15)
      self.assertEqual(proc.returncode,0)
      if malformed:
       self.assertNotIn('Copied to DOS',out);self.assertEqual(int(out.split()[0]),0)
       self.assertEqual(disk,before)
      else:self.assertIn('Copied to DOS',out)
     finally:
      if proc.poll() is None:proc.kill();proc.wait()
      proc.stdin.close();proc.stdout.close()
     if malformed:continue
     self.disk.write_bytes(disk)
     self.assertEqual(read_files(disk)['KEEP'],read_files(before)['KEEP'])
     expected=b'\x00\x20'+size.to_bytes(2,'little')+self.payload
     self.assertEqual(read_files(disk)['NEW']['data'],expected+bytes((-len(expected))%256))
 def test_preflight_refusals_write_nothing(self):
  for mode in (1,2,6,12,15,17,19,20,21):
   self.disk.write_bytes(self.original);self.assertEqual(self.run_op(mode)[0],0)
   self.assertEqual(self.disk.read_bytes(),self.original)
 def test_bad_metadata_and_collisions(self):
  fixtures=[]
  b=bytearray(self.original);b[offset(17,0)+0x34]=40;fixtures.append(b)
  b=bytearray(self.original);b[offset(17,15)+1:offset(17,15)+3]=bytes([17,15]);fixtures.append(b)
  b=bytearray(self.original);b[offset(17,0)+0x38+3*4+1]|=1;fixtures.append(b)
  b=bytearray(self.original);b[offset(17,15)+11+33]=99;fixtures.append(b)
  fixtures.append(make_disk([('NEW',0,b'old')]))
  b=bytearray(self.original);b[offset(17,0)+0x38:offset(17,0)+0x38+140]=bytes(140);fixtures.append(b)
  for fixture in fixtures:
   self.disk.write_bytes(fixture);self.assertEqual(self.run_op()[0],0);self.assertEqual(self.disk.read_bytes(),fixture)
 def test_source_errors_and_cancel_never_publish(self):
  for mode in (7,8,9,10,11,18):
   with self.subTest(mode=mode):
    self.disk.write_bytes(self.original);_,out=self.run_op(mode);self.assertIn('stopped',out)
    self.assert_keep();self.assertNotIn('NEW',read_files(self.disk.read_bytes()))
 def test_malformed_catalog_end_and_ts_offsets_write_nothing(self):
  before=make_disk([('KEEP',0x80,b'K'*32000)])
  for at,value in ((48*256+5,1),(49*256+5,0),(offset(17,1)+1,17)):
   with self.subTest(at=at):
    bad=bytearray(before);bad[at]=value;self.disk.write_bytes(bad)
    writes,out=self.run_op()
    self.assertEqual(writes,0)
    self.assertNotIn('Copied to DOS',out)
    self.assertEqual(self.disk.read_bytes(),bad)
  self.disk.write_bytes(before);_,out=self.run_op()
  self.assertIn('Copied to DOS',out)
  self.assertEqual(read_files(self.disk.read_bytes())['KEEP'],read_files(before)['KEEP'])
 def test_each_failed_write_stops_without_retry(self):
  count,_=self.run_op()
  for at in range(1,count+1):
   self.disk.write_bytes(self.original);written,out=self.run_op(3,at)
   self.assertEqual(written,at);self.assertIn('stopped',out);self.assert_keep()
   self.assertNotIn('NEW',read_files(self.disk.read_bytes()))
 def test_read_failures_preserve_existing_files(self):
  _,out=self.run_op();reads=int(out.split()[1])
  for at in range(1,reads+1):
   self.disk.write_bytes(self.original);_,out=self.run_op(2,at)
   self.assertNotIn('Copied to DOS',out)
   self.assert_keep()
 def test_silent_corruption_stops_at_readback(self):
  count,_=self.run_op()
  for at in range(1,count+1):
   self.disk.write_bytes(self.original);written,out=self.run_op(5,at)
   self.assertEqual(written,at);self.assertIn('stopped',out)
   # Raw sector tearing may damage a shared metadata sector; there must be
   # no retry or source removal, even when WRITE_BLOCK claimed success.
 def test_retry_after_unpublished_failure_uses_new_sectors(self):
  self.run_op(3,3)
  failed=self.disk.read_bytes()
  _,out=self.run_op();self.assertIn('Copied to DOS',out);self.assert_keep()
  before=failed[offset(17,0):offset(17,0)+256]
  after=self.disk.read_bytes()[offset(17,0):offset(17,0)+256]
  for i in range(0x38,0x38+140):self.assertEqual(after[i]&~before[i],0)
 def test_oversized_and_unsupported_sources_write_nothing(self):
  self.payload=b'X'*65536;self.src.write_bytes(self.payload)
  self.assertEqual(self.run_op()[0],0);self.assertEqual(self.disk.read_bytes(),self.original)
  self.payload=b'X';self.src.write_bytes(self.payload)
  self.assertEqual(self.run_op(kind=255)[0],0);self.assertEqual(self.disk.read_bytes(),self.original)
 def test_partial_write_is_not_retried(self):
  # Physical catalog/VTOC tearing is not atomic; inspect exact write count,
  # source retention and the independent existing data-sector bytes.
  count,_=self.run_op()
  old=read_files(self.original)['KEEP']
  for at in range(1,count+1):
   self.disk.write_bytes(self.original);written,out=self.run_op(4,at)
   self.assertEqual(written,at);self.assertIn('stopped',out)
   result=self.disk.read_bytes()
   for t,s in old['blocks']+old['lists']:
    pos=offset(t,s);self.assertEqual(result[pos:pos+256],self.original[pos:pos+256])
if __name__=='__main__':unittest.main()
