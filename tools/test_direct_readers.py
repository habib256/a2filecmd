"""Real DOS/ProDOS reader C, read-only backends, faults and HGR handoff."""
import re, shutil, subprocess, tempfile, unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from test_fontrix import fixture
from test_sample_media import clip_page
from mini33_fixture import make_disk, offset
from mos6502 import CPU
ROOT=D.ROOT

H=BASE.replace('#include "src/plugins/dosint.c"','#include READER_SOURCE')
H=H.replace('api.cgetc=key;', 'api.media_wait=key;api.cgetc=key;')
H=H.replace('static void bar(', '''
#ifdef TEST_CLIP
void hv_clear(void){}
void hv_show(void){++shown;fwrite(ps_bitmap,1,572,stdout);}
void __fastcall__ ps_draw(unsigned char* p){(void)p;}
#endif
static void bar(''')

class DirectReaders(unittest.TestCase):
 run_disk=D.Streams.run_disk
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='direct-readers-',dir='/tmp');cls.p=Path(cls.tmp.name)
  cls.h=cls.p/'h.c';cls.h.write_text(H);cls.executables={}
  for name in ('printshop','fontrix'):
   exe=cls.p/name
   subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),'-DREADER_SOURCE="src/plugins/'+name+'.c"',*(['-DTEST_CLIP'] if name=='printshop' else []),str(cls.h),'-o',str(exe)],check=True,capture_output=True)
   cls.executables[name]=exe
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def disk(self,b):return make_disk([('TEXT',4,b'\0H'+len(b).to_bytes(2,'little')+b)])
 def test_all_backends_stale_sizes_and_complete_read_errors(self):
  for name,b in (('printshop',bytes((i*37)&255 for i in range(572))),('fontrix',fixture())):
   self.exe=self.executables[name]
   for image in (0,1,2):
    outputs=[]
    for size in (0,1,0xffffff):
     out,counts,_=self.run_disk(self.disk(b),typ=6,image=image,size=size);outputs.append(out)
     if name=='printshop':self.assertEqual(out,b)
     else:self.assertIn(b'Fontrix: A',out)
    self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])
    for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
     out,_,_=self.run_disk(self.disk(b),typ=6,image=image,fault=fault,good=False)
     self.assertEqual(out,b'')
 def test_malformed_lengths_pointers_and_catalog(self):
  for name,b in (('printshop',bytes(572)),('fontrix',fixture())):
   self.exe=self.executables[name]
   for n in (0,1,len(b)//2,len(b)-1):self.run_disk(self.disk(b[:n]),typ=6,good=False)
   if name=='printshop':
    self.run_disk(self.disk(b+bytes(4)),typ=6)
    self.run_disk(self.disk(b+b'X'),typ=6,good=False)
    self.run_disk(self.disk(b+bytes(5)),typ=6,good=False)
   else:
    bad=bytearray(b);bad[102:104]=b'\xff\xff';self.run_disk(self.disk(bad),typ=6,good=False)
   disk=bytearray(self.disk(b));disk[offset(17,15)+14]^=1
   self.run_disk(disk,typ=6,key=783,good=False)
   self.run_disk(self.disk(b),typ=4,good=False)
 def test_cc65_both_cpus(self):
  if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
  root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
  for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
   cfg=self.p/(target+'.cfg');cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
   for name,b in (('printshop',bytes((i*37)&255 for i in range(572))),('fontrix',fixture(height=32))):
    exe=self.p/(name+cpu)
    subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DREADER_SOURCE="src/plugins/'+name+'.c"',*(['-DTEST_CLIP'] if name=='printshop' else []),'-o',str(exe),str(self.h)],check=True,capture_output=True)
    self.exe=self.executables[name]
    for image in (0,1,2):
     expected,counts,_=self.run_disk(self.disk(b),typ=6,image=image)
     actual,_,_=self.run_disk(self.disk(b),typ=6,image=image,exe=exe);self.assertEqual(actual,expected)
     for fault in (1,counts[1],*([1002,1003,1004] if image else [])):
      out,_,_=self.run_disk(self.disk(b),typ=6,image=image,exe=exe,fault=fault,good=False);self.assertEqual(out,b'')

class Routing(unittest.TestCase):
 def test_actual_ident_classifier_for_dos_and_prodos(self):
  import ctypes
  from corpus_census import C_SOURCE
  from test_purple import planes
  with tempfile.TemporaryDirectory(prefix='direct-ident-') as tmp:
   p=Path(tmp);(p/'id.c').write_text(C_SOURCE)
   for cpu in ('6502','65c02'):
    libpath=p/(cpu+'.so')
    subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),*(['-DA2FC_6502'] if cpu=='6502' else []),str(p/'id.c'),'-o',str(libpath)],check=True,capture_output=True)
    fn=ctypes.CDLL(str(libpath)).corpus_ident
    fn.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];fn.restype=ctypes.c_char_p
    for dos in (0,1):
     for name,typ,b,expected in [('SAMPLE.S',4,b'\xa0\xcc\xc4\xc1\xa0\xa3\xb0\x8d','MERLIN'),('SAMPLE.ASM',4,b'\xaa\xc8\xc9\x8d','MERLIN'),('SAMPLE.S',4,b'ordinary text\r','DOSVIEW' if dos else None),('SAMPLE.S',6,b'\xaa\xc8\xc9\x8d','DOSVIEW' if dos else 'MERLIN')]:
      out=ctypes.create_string_buffer(80);fn(name.encode(),typ,0,b,len(b),dos,out)
      if expected:self.assertEqual(out.value.decode(),expected)
      else:self.assertNotEqual(out.value.decode(),'MERLIN')
     for name,aux,b,expected in [('CLIP',0x4800,bytes(572),'PRINTSHOP'),('SET.TEST',0x6400,fixture(),'FONTRIX'),('FRENCH.FONT',0x6100,bytes(768),'DOSFONT' if dos else 'FONTVIEW'),('APPLE.SET',0x2000,bytes(1024),'DOSFONT' if dos else 'FONTVIEW'),('FAKE.FONT',0x6100,bytes(769),None),('CLIP',0x4800,bytes(571),None),('UNKNOWN',0,bytes(300),None)]:
      out=ctypes.create_string_buffer(80);fn(name.encode(),6,aux,b,len(b),dos,out)
      if expected:self.assertEqual(out.value.decode(),expected)
      else:self.assertNotIn(out.value.decode(),('PRINTSHOP','FONTRIX'))
     # Both entry names own the pair; generic raw pages still use IMAGE.
     # DOS has no direct pair reader and must keep the DOSVIEW refusal.
     for name,body in zip(('PAIR.FOTO1','PAIR.FOTO2'),planes(5)):
      original=bytes(bytearray(body));out=ctypes.create_string_buffer(80)
      self.assertTrue(fn(name.encode(),6,0x2000,body,len(body),dos,out))
      self.assertEqual(out.value.decode(),'DOSVIEW' if dos else 'PURPLE')
      self.assertEqual(body,original)
     for name in ('ORDINARY','PAIR.FOTO3'):
      body=planes(5)[1];out=ctypes.create_string_buffer(80)
      self.assertTrue(fn(name.encode(),6,0x2000,body,len(body),dos,out))
      self.assertEqual(out.value.decode(),'DOSVIEW' if dos else 'IMAGE')

class ClipRenderer(unittest.TestCase):
 def test_native_handoff_full_page_stack_and_both_cpus(self):
  b=bytes((i*37)&255 for i in range(572))
  for arch,d in (('enh','build'),('6502','build-6502')):
   subprocess.run(['make','ARCH='+arch,d+'/printshop.PLG'],cwd=ROOT,check=True,capture_output=True)
   labels={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/'printshop.lbl').read_text())}
   labels['sp']=labels.get('sp',labels.get('c_sp'))
   class Guest(CPU):
    def fetch(c):
     if 0x2000<=c.pc<0x4000 and c.pc!=labels['_ps_preflight']:raise AssertionError('executed overwritten HGR memory')
     return super().fetch()
   for accepted in (False,True):
    c=Guest();c.m[:]=bytes([0xa5])*65536;plugin=(ROOT/d/'printshop.PLG').read_bytes();c.m[0x1b00:0x1b00+len(plugin)]=plugin
    c.m[labels['_ps_bitmap']:labels['_ps_bitmap']+572]=b
    c.m[labels['sp']:labels['sp']+2]=(0xb000).to_bytes(2,'little')
    c.m[0x1066:0x1068]=(0x6000).to_bytes(2,'little');c.m[0x6000]=2;c.m[labels['_ps_preflight']]=2
    before=bytes(c.m[0x2000:0x4000])
    def trap():
     if c.pc-1==labels['_ps_preflight']:c.a=int(accepted);c.x=0
     else:self.assertEqual(c.pc-1,0x6000);self.assertEqual(bytes(c.m[0x2000:0x4000]),clip_page(b))
     c.ops[0x60]()
    c.ops[2]=trap;c.a=0;c.x=0x10;c.call(labels['_plugin_entry'])
    self.assertEqual(int.from_bytes(c.m[labels['sp']:labels['sp']+2],'little'),0xb000)
    if not accepted:self.assertEqual(bytes(c.m[0x2000:0x4000]),before)

if __name__=='__main__':unittest.main()
