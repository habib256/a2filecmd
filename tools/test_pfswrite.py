"""Actual PFS:Write C: originals, lengths, preserved controls and I/O faults."""
import ctypes,hashlib,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_retrotext import HARNESS,ROOT
H=HARNESS.replace('e.size=strtoul(argv[4],0,10);','e.size=strtoul(argv[4],0,10);e.type=atoi(argv[5]);e.aux=atoi(argv[6]);').replace('if(fault==1)return NULL;','if(fault==1 || (fault==7 && opens==2))return NULL;').replace('(fault==5 && opens==2)','(fault==5 && opens==2)||(fault==6 && reads==5)')

def pfs(text=b'Hello\r'):
    body=b'\x0c\r'+text+b'\x0e';h=bytearray(1024);h[:6]=b'B\0\x06\0\x06\0';h[6:8]=body.count(13).to_bytes(2,'little');h[8:10]=len(body).to_bytes(2,'little');return bytes(h)+body

def originals():
    from corpus_read import images,files
    root=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus'));seen=set()
    for p in sorted((root/'images').rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.dsk','.po','.zip'):continue
        for member,data in images(p):
            try:fs,entries=files(data)
            except ValueError:continue
            for n,t,a,d in entries:
                digest=hashlib.sha256(d).hexdigest()
                if t==22 and a==2 and digest not in seen:
                    seen.add(digest);yield p,member,n,d

class PfsWrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pfswrite-tests-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfswrite.c"',str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,d,fault=0,keys='',size=1,typ=22,aux=2,refused=False,exe=None):
        src=self.p/'source';src.write_bytes(d);args=[str(src),str(fault),keys,str(size),str(typ),str(aux)]
        r=subprocess.run(([str(self.exe)] if exe is None else exe)+args,check=True,capture_output=True,text=True,timeout=30)
        self.assertEqual(src.read_bytes(),d);op,cl,note=r.stderr.rstrip('\n').split(' ',2);rows=[s[1:].rstrip() for s in r.stdout.splitlines() if s.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        else:self.assertEqual(note,'',r.stderr)
        return rows,(int(op),int(cl)),note
    def test_plain_highbit_controls_and_page_breaks(self):
        rows,_,_=self.run_file(pfs(b'Hello\r\xc1\x81\xe2\x81\r\x09X\x0cY\x80\r'))
        self.assertEqual([r for r in rows if r],['Hello','A^Ab^A','^IX^LY^@'])
    def test_real_documents(self):
        docs=list(originals());self.assertEqual(len(docs),8)
        for _,_,n,d in docs:
            rows,_,_=self.run_file(d);self.assertTrue(any(rows),n)
        annual=next(d for _,_,n,d in docs if n=='/ANNUAL.PFS');rows,_,_=self.run_file(annual)
        self.assertTrue(any('A^Ag^Ae^An^At^A' in r for r in rows))
    def test_whole_file_validation_before_display(self):
        good=pfs(b'Hello\r')
        for n in (0,1,5,9,512,1023,1024,len(good)-1):self.run_file(good[:n],refused=True)
        for i,v in ((6,0),(8,1),(1024,13),(1025,32),(1026,0),(1026,14),(1026,127),(1026,255),(-1,0)):
            d=bytearray(good);d[i]=v;self.run_file(bytes(d),refused=True)
        self.run_file(good+b'X',refused=True)
        self.run_file(pfs(b'X\r'*100)+b'X',refused=True)
    def test_metadata_stale_sizes_and_limit(self):
        # Page/printer settings do not participate in plain-text decoding.
        d=bytearray(pfs());d[:6]=b'\x84\0\0\0\x03\0';d[10:1024]=b'\xa5'*1014
        rows,_,_=self.run_file(bytes(d));self.assertIn('Hello',rows)
        for typ,aux in ((6,2),(22,1),(22,4),(22,22)):
            self.run_file(pfs(),typ=typ,aux=aux,refused=True)
        for size in (0,1,999999):self.run_file(pfs(),size=size)
        self.run_file(pfs(b'X'*64508));self.run_file(pfs(b'X'*64509),refused=True)
    def test_actual_identifier_routes_write_only(self):
        from corpus_census import C_SOURCE
        source=self.p/'ident.c';source.write_text(C_SOURCE);libpath=self.p/'ident.so'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),str(source),'-o',str(libpath)],check=True,capture_output=True)
        identify=ctypes.CDLL(str(libpath)).corpus_ident
        identify.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];identify.restype=ctypes.c_char_p
        d=pfs();buf=ctypes.create_string_buffer(d)
        for typ,aux,dos,expected in ((22,2,0,True),(22,1,0,False),(22,4,0,False),(22,22,0,False),(6,2,0,False),(22,2,1,False)):
            out=ctypes.create_string_buffer(64);label=identify(b'DOCUMENT',typ,aux,buf,len(d),dos,out)
            self.assertIsNotNone(label);self.assertEqual(out.value==b'PFSWRITE',expected)
        for _,_,_,d in originals():
            out=ctypes.create_string_buffer(64);buf=ctypes.create_string_buffer(d)
            self.assertEqual(identify(b'NO.SUFFIX',22,2,buf,len(d),0,out),b'PFS:Write?');self.assertEqual(out.value,b'PFSWRITE')
    def test_all_io_faults_and_cancel(self):
        d=pfs(b'Line\r'*200)
        for fault in range(1,8):
            src=self.p/'source';src.write_bytes(d)
            r=subprocess.run([str(self.exe),str(src),str(fault),'','0','22','2'],check=True,capture_output=True,text=True)
            self.assertIn('error',r.stderr);self.assertEqual(src.read_bytes(),d)
            if fault in (1,2,3,6,7):self.assertNotIn('|Line',r.stdout)
        rows,counts,_=self.run_file(d,keys='E');self.assertEqual(sum(r=='Line' for r in rows),20);self.assertEqual(counts,(2,2))
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        samples=[pfs(b'Hello\r\xc1\x81\r'),pfs(b'X'*64508)]+[d for _,_,_,d in originals()]
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1));exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfswrite.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
            for d in samples:
                expected=self.run_file(d);actual=self.run_file(d,exe=['sim65',str(exe)]);self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
