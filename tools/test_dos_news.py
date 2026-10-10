"""Execute the DOS Newsroom C preflight and real native renderer."""
import re,subprocess,tempfile,unittest,shutil,random
from pathlib import Path
from test_dos_hgr import HGR
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from mini33_fixture import make_disk
from newsroom_ref import make,parse,page
ROOT=D.ROOT
HARNESS=BASE.replace('src/plugins/dosint.c','src/plugins/dosnews.c')
HARNESS=HARNESS.replace('static void bar(', 'void host_news(const unsigned char* p,unsigned int n,unsigned char w,unsigned char h){++shown;fwrite(p,1,n,stdout);}\nstatic void bar(')

class Preflight(unittest.TestCase):
 run_disk=D.Streams.run_disk
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='dosnews-',dir='/tmp');cls.p=Path(cls.tmp.name);cls.h=cls.p/'test.c';cls.h.write_text(HARNESS);cls.exe=cls.p/'host'
  subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def disk(self,b):return make_disk([('TEXT',4,b'\0@'+len(b).to_bytes(2,'little')+b)])
 def test_exact_bytes_and_all_faults(self):
  for wb,h in ((1,1),(35,80),(37,192)):
   b=make(random.Random(17),wb,h,history=b'\xff'*500)
   for image in (0,1,2):
    out,counts,_=self.run_disk(self.disk(b),typ=6,image=image);self.assertEqual(out,bytes(c&127 for c in parse(b)[2]))
    for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
     out,_,_=self.run_disk(self.disk(b),typ=6,image=image,fault=fault,good=False);self.assertEqual(out,b'')
 def test_malformed_and_original_ph_bn_corpus(self):
  b=make(random.Random(9),3,5)
  for bad in [b[:i] for i in range(len(b))]+[b[:2]+bytes((8,7))+b[4:],b[:4]+bytes((9,8))+b[6:],b[:6]+b'X'+b[7:]]:
   try:parse(bad)
   except ValueError:self.run_disk(self.disk(bad),typ=6,good=False)
  from legacy_corpus import dos_files
  root=Path.home()/'.cache/a2fc/newsroom/ia';seen=set()
  for p in root.glob('*'):
   try:files=list(dos_files(p.read_bytes()))
   except (ValueError,OSError):continue
   for nm,t,a,b in files:
    if nm.startswith(('PH.','BN.')) and b not in seen:
     seen.add(b);out,_,_=self.run_disk(self.disk(b),typ=6,image=1);self.assertEqual(out,bytes(c&127 for c in parse(b)[2]))
  self.assertGreater(len(seen),50)

class Renderer(HGR):
 @classmethod
 def setUpClass(cls):
  cls.builds=[]
  for arch,d in (('enh','build'),('6502','build-6502')):
   subprocess.run(['make','ARCH='+arch,d+'/dosnews.PLG'],cwd=ROOT,check=True,capture_output=True)
   labels={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/'dosnews.lbl').read_text())}
   cls.builds.append(((ROOT/d/'dosnews.PLG').read_bytes(),labels))
 def test_exact_pages_on_both_cpus_and_backends(self):
  for build in self.builds:
   for shape in ((1,1,1),(35,80,19),(37,192,241),(3,25,248),(1,192,256)):
    for image,base in ((False,0),(True,0),(True,64),(True,0x20345)):
     self.run_loader(build,image=image,base=base,news=shape)
 def test_each_read_seek_error_and_close_before_display(self):
  for build in self.builds:
   for image in (False,True):
    counts=self.run_loader(build,image=image,news=(37,192,241))
    for n in range(1,counts['read']+1):
     self.run_loader(build,image=image,news=(37,192,241),fault=('read',n))
     if image:
      self.run_loader(build,image=True,news=(37,192,241),fault=('seek',n))
      self.run_loader(build,image=True,news=(37,192,241),fault=('ferror',n))
   self.run_loader(build,image=True,news=(37,192,241),fault=('close',1))
if __name__=='__main__':unittest.main()
