"""Real DOS font adapter C and shared FONTVIEW renderer; immutable inputs."""
import re, shutil, subprocess, tempfile, unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from test_fontview import raw_page
from mini33_fixture import make_disk,offset
from mos6502 import CPU
ROOT=D.ROOT
H=BASE.replace('#include "src/plugins/dosint.c"','#include "src/plugins/dosfont.c"')
H=H.replace('static void bar(','''void host_font(const unsigned char* p,unsigned int n){
 if(df_buf!=buffer || memcmp(df_buf,p,512) || memcmp(df_tail,p+512,n-512))abort();
 ++shown;fwrite(p,1,n,stdout);
}
static void bar(''')

def font(n):return bytes((i*13+i//8)&255 for i in range(n))

def disk(b):return make_disk([('TEXT',4,b'\0a'+len(b).to_bytes(2,'little')+b)])

class Source(unittest.TestCase):
 run_disk=D.Streams.run_disk
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='dosfont-',dir='/tmp');cls.p=Path(cls.tmp.name);cls.h=cls.p/'h.c';cls.h.write_text(H);cls.exe=cls.p/'host'
  subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_exact_bytes_all_backends_and_stale_sizes(self):
  for n in (768,1024):
   b=font(n)
   for image in (0,1,2):
    for size in (0,1,0xffffff):
     out,counts,_=self.run_disk(disk(b),typ=6,image=image,size=size)
     self.assertEqual(out,b);self.assertEqual(counts[4],1)
 def test_every_read_open_seek_close_error_before_display(self):
  for image in (0,1,2):
   _,counts,_=self.run_disk(disk(font(1024)),typ=6,image=image)
   for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
    out,counts,_=self.run_disk(disk(font(1024)),typ=6,image=image,fault=fault,good=False)
    self.assertEqual(out,b'');self.assertEqual(counts[4],0)
 def test_malformed_lengths_catalog_aliases_and_selection(self):
  for n in (0,1,767,769,1023,1025,2048):self.run_disk(disk(font(n)),typ=6,good=False)
  raw=disk(font(1024))
  bad=bytearray(raw);bad[offset(17,15)+14]^=1
  self.run_disk(bad,typ=6,key=783,good=False)
  bad=bytearray(raw);p=offset(3,15);bad[p+14:p+16]=bad[p+12:p+14]
  self.run_disk(bad,typ=6,good=False)
  self.run_disk(raw,typ=4,good=False)
 def test_real_hrcg_corpus_when_available(self):
  import json,hashlib
  index=Path.home()/'.cache/a2fc/asimov_corpus/index.json'
  if not index.exists():self.skipTest('local HRCG corpus unavailable')
  rows=json.loads(index.read_text())['rows'];seen=set()
  for row in rows:
   if row.get('fs')!='dos' or row.get('type')!='B' or row.get('length') not in (768,1024) or not row.get('name','').endswith(('.SET','.FONT')):continue
   for directory,name in row.get('saved',{}).items():
    if '/hrcg/' not in directory:continue
    p=Path(directory)/name
    if not p.exists():continue
    b=p.read_bytes()
    self.assertEqual(hashlib.sha1(b).hexdigest(),row['sha1']);self.assertEqual(len(b),row['length'])
    if b in seen:continue
    seen.add(b);out,_,_=self.run_disk(disk(b),typ=6,image=1);self.assertEqual(out,b)
  if not seen:self.skipTest('saved HRCG corpus unavailable')
  self.assertTrue(seen)
 def test_cc65_both_cpus_and_io_faults(self):
  if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
  root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
  for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
   cfg=self.p/(target+'.cfg');cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
   exe=self.p/target
   subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
   for image in (0,1,2):
    for n in (768,1024):
     out,counts,_=self.run_disk(disk(font(n)),typ=6,image=image,exe=exe);self.assertEqual(out,font(n))
     for fault in (1,counts[1],*([1002,1003,1004] if image else [])):
      out,counts,_=self.run_disk(disk(font(n)),typ=6,image=image,exe=exe,fault=fault,good=False);self.assertEqual(out,b'');self.assertEqual(counts[4],0)

class Renderer(unittest.TestCase):
 def test_handoff_whole_page_stack_bounds_and_both_cpus(self):
  for arch,d in (('enh','build'),('6502','build-6502')):
   subprocess.run(['make','ARCH='+arch,d+'/dosfont.PLG'],cwd=ROOT,check=True,capture_output=True)
   labels={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/'dosfont.lbl').read_text())}
   sp=labels.get('sp',labels.get('c_sp'))
   class Guest(CPU):
    def fetch(c):
     if 0x2000<=c.pc<0x4000 and c.pc!=labels['_df_preflight']:raise AssertionError('executed overwritten HGR memory')
     return super().fetch()
   for n in (768,1024):
    for accepted in (False,True):
     b=font(n);c=Guest();c.m[:]=bytes([0xa5])*65536;plugin=(ROOT/d/'dosfont.PLG').read_bytes();c.m[0x1b00:0x1b00+len(plugin)]=plugin
     c.m[0x1200:0x1400]=b[:512];c.m[labels['_df_tail']:labels['_df_tail']+n-512]=b[512:]
     c.m[labels['_df_buf']:labels['_df_buf']+2]=(0x1200).to_bytes(2,'little');c.m[labels['_df_count']]=n//8
     c.m[sp:sp+2]=(0xb000).to_bytes(2,'little');c.m[0x1022:0x1024]=(0x6000).to_bytes(2,'little');c.m[0x6000]=2;c.m[labels['_df_preflight']]=2
     before=bytes(c.m[0x2000:0x4000]);shown=[]
     def trap():
      if c.pc-1==labels['_df_preflight']:c.a=int(accepted);c.x=0
      else:
       self.assertEqual(c.pc-1,0x6000);self.assertEqual(bytes(c.m[0x2000:0x4000]),raw_page(b));shown.append(True)
      c.ops[0x60]()
     c.ops[2]=trap;c.x=0x10;c.call(labels['_plugin_entry'])
     self.assertEqual(int.from_bytes(c.m[sp:sp+2],'little'),0xb000)
     self.assertEqual(bool(shown),accepted);self.assertEqual(bytes(c.m[0x1200:0x1400]),b[:512])
     if not accepted:self.assertEqual(bytes(c.m[0x2000:0x4000]),before)

if __name__=='__main__':unittest.main()
