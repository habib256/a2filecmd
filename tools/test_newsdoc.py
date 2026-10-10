"""Actual PN/PG C decoders on ProDOS and all read-only DOS backends."""
import subprocess,tempfile,unittest,shutil
from pathlib import Path
from test_retrotext import HARNESS as PRO
from test_dosint import HARNESS as DOS
import test_dos_stream as D
from mini33_fixture import make_disk
ROOT=D.ROOT

def panel(text=b'Headline\x8dBody text\r\x7f',photos=1):
 return len(text).to_bytes(2,'little')+bytes((0,1,0,0,photos))+bytes(5*photos)+b'PHOTO'.ljust(8,b'\0')*photos+text

def page(layout=0):
 return bytes((layout,))+b'BANNER'.ljust(8,b'\0')+b'PANEL'.ljust(8,b'\0')*9+b'PAGE'.ljust(8,b'\0')+bytes(range(10))

class NewsDoc(unittest.TestCase):
 run_disk=D.Streams.run_disk
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='newsdoc-',dir='/tmp');cls.p=Path(cls.tmp.name);cls.exes={};cls.sim={}
  for name in ('newspan','newspage'):
   for backend in ('pro','dos'):
    h=cls.p/(name+backend+'.c');h.write_text(PRO if backend=='pro' else DOS.replace('src/plugins/dosint.c','src/plugins/'+name+'.c'))
    exe=cls.p/(name+backend)
    args=['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT)]
    if backend=='pro':args+=['-DRT_SOURCE="src/plugins/'+name+'.c"']
    subprocess.run(args+[str(h),'-o',str(exe)],check=True,capture_output=True);cls.exes[name,backend]=exe
  if shutil.which('cl65'):
   targets=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
   for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
    cfg=(targets/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1)
    config=cls.p/(cpu+'.cfg');config.write_text(cfg)
    for name in ('newspan','newspage'):
     exe=cls.p/(name+cpu);h=cls.p/(name+'dos.c')
     subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(h)],check=True,capture_output=True);cls.sim[name,cpu]=exe
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def dos(self,name,data,image=0,fault=0,good=True,exe=None,keys='N'*100,size=1):
  self.exe=self.exes[name,'dos'];aux=0x4000 if name=='newspan' else 0x98a5
  disk=make_disk([('TEXT',4,aux.to_bytes(2,'little')+len(data).to_bytes(2,'little')+data)])
  return self.run_disk(disk,typ=6,image=image,fault=fault,good=good,exe=exe,keys=keys,size=size)
 def pro(self,name,data,fault=0,good=True,keys='N'*100):
  src=self.p/'source';src.write_bytes(data)
  r=subprocess.run([str(self.exes[name,'pro']),str(src),str(fault),keys,'1'],check=True,capture_output=True,text=True)
  self.assertEqual(src.read_bytes(),data);note=r.stderr.rstrip('\n').split(' ',2)[2]
  self.assertEqual(bool(note),not good,r.stderr)
  if not good and fault!=4:self.assertNotIn('PAGE',r.stdout)
  return r.stdout
 def test_exact_content_all_backends_both_cpus(self):
  for name,data,need in (('newspan',panel(),b'Headline'),('newspage',page(),b'BN.BANNER')):
   self.assertIn(need.decode(),self.pro(name,data))
   for image in (0,1,2):
    for size in (0,1,0xffffff):
     out,_,_=self.dos(name,data,image=image,size=size);self.assertIn(need,out)
    for cpu in ('6502','65c02'):
     out,_,_=self.dos(name,data,image=image,exe=self.sim[name,cpu]);self.assertIn(need,out)
 def test_all_truncations_trailing_data_and_bad_headers(self):
  for name,data in (('newspan',panel()),('newspage',page())):
   for n in range(len(data)):
    self.pro(name,data[:n],good=False);self.dos(name,data[:n],good=False)
   self.pro(name,data+b'X',good=False);self.dos(name,data+b'X',good=False)
  for data in (panel(b'bad\x01'),panel()[:2]+b'\3'+panel()[3:],page(4)):
   name='newspage' if len(data)==99 else 'newspan';self.pro(name,data,good=False);self.dos(name,data,good=False)
 def test_every_source_read_and_close_failure(self):
  for name,data in (('newspan',panel(b'Line\r'*200)),('newspage',page())):
   for fault in (1,3,4,5):self.pro(name,data,fault=fault,good=False)
   for image in (0,1,2):
    _,counts,_=self.dos(name,data,image=image)
    for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):self.dos(name,data,image=image,fault=fault,good=False)
 def test_original_corpus(self):
  from legacy_corpus import dos_files
  root=Path.home()/'.cache/a2fc/newsroom';seen=set();counts=[0,0]
  for p in list(root.glob('*.dsk'))+list((root/'ia').glob('*')):
   try:files=list(dos_files(p.read_bytes()))
   except (ValueError,OSError):continue
   for nm,t,aux,data in files:
    if not nm.startswith(('PN.','PG.')) or data in seen:continue
    seen.add(data);name='newspan' if nm.startswith('PN.') else 'newspage';counts[name=='newspage']+=1
    self.pro(name,data);self.dos(name,data,image=1)
  if not seen:self.skipTest('local Newsroom corpus unavailable')
  self.assertGreaterEqual(counts[0],78);self.assertGreaterEqual(counts[1],22)
 def test_maximum_text_paging_cancel_and_modes(self):
  data=panel(b'A'*65528,photos=0)
  out,_,_=self.dos('newspan',data,keys='N'*1000);self.assertEqual(out.count(b'A'),65528)
  for cpu in ('6502','65c02'):self.dos('newspan',data,keys='N'*1000,exe=self.sim['newspan',cpu])
  out,_,_=self.dos('newspan',panel(b'A\r'*100),keys='E');self.assertNotIn(b'End - press',out)
  for layout in range(4):
   out,_,_=self.dos('newspage',page(layout));self.assertIn(b'without banner' if layout&1 else b'with banner',out)
if __name__=='__main__':unittest.main()
