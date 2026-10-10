"""PFS:Plan actual-C validation, stored decimal values and source preservation."""
import ctypes,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_retrotext import ROOT
from test_pfswrite import H

def originals():
 from corpus_read import files
 root=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus'))/'images/productivity/integrated/pfs/PFS Plan.po'
 return [(n,d) for n,t,a,d in files(root.read_bytes())[1] if t==22 and a==4]

def sheet():
 d=bytearray(4608);d[:4]=b'\x01\0\x01\0';d[24:34]=b'Plan  \x03B00';d[1024:1034]=b'\0\0\x80\0\x05Costs';d[1536:1553]=b'\0\x04\0\0\0\x80\x0b\0\x01\x03Jul\x01\0\x01\0';d[2048:2054]=b'\x12\x34\x50\0\0\x03';d[2560]=1;d[3072]=1;return bytes(d)

class PfsPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pfsplan-tests-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfsplan.c"',str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,d,fault=0,keys='',size=1,typ=22,aux=4,refused=False,exe=None):
        src=self.p/'source';src.write_bytes(d);args=[str(src),str(fault),keys,str(size),str(typ),str(aux)]
        r=subprocess.run(([str(self.exe)] if exe is None else exe)+args,check=True,capture_output=True,text=True,timeout=30)
        self.assertEqual(src.read_bytes(),d);op,cl,note=r.stderr.rstrip('\n').split(' ',2);rows=[s[1:].rstrip() for s in r.stdout.splitlines() if s.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        else:self.assertEqual(note,'',r.stderr)
        return rows,(int(op),int(cl)),note
    def test_real_sheets(self):
        docs=originals();self.assertEqual(len(docs),6)
        for n,d in docs:
            rows,_,_=self.run_file(d);self.assertTrue(any(rows),n)
        rows,_,_=self.run_file(dict(docs)['/COSTS.PFS']);self.assertIn(' C1 Jul = 1371',rows);self.assertIn('R8 Total Gen&Admin Expenses',rows);self.assertIn('R8 formula: @Total Gen&Admin Expenses',rows);self.assertIn('C7 formula: @Total',rows)
        rows,_,_=self.run_file(dict(docs)['/CASH.PFS']);self.assertIn(' C1 Qtr1 = -14855 [formula]',rows)
        rows,_,_=self.run_file(dict(docs)['/SALES.PFS']);self.assertIn(' C1 Forecast = 4311',rows)
    def test_decimal_and_blank(self):
        for value,expected in [(b'\x12\x34\x50\0\0\x03','123.45'),(b'\x12\x34\x50\0\0\x13','-123.45'),(b'\x75\0\0\0\0\0','0.75'),(bytes(5)+b'\x20','0'),(b'\xa0'+bytes(5),'[blank]'),(b'\x12\x34\x50\0\0\x43','123.45 [formula]')]:
            d=bytearray(sheet());d[2048:2054]=value;rows,_,_=self.run_file(bytes(d));self.assertIn(' C1 Jul = '+expected,rows)
    def test_maximum_dimensions_and_block_boundaries(self):
        d=bytearray(7168);d[:4]=b'\x20\0\x10\0';d[24:34]=b'Plan  \x03B00'
        for i in range(32):d[1024+i*5:1029+i*5]=b'\0\0\x80\0\0'
        for i in range(16):d[1536+i*17:1553+i*17]=b'\0\x04\0\0\0\x80\x0b\0\x01\x03Jul\x01\0\x01\0'
        for i in range(512):d[2048+i*6:2054+i*6]=b'\x12\x34\x50\0\0\x0a'
        d[5120:5152]=bytes([1])*32;d[5632:5648]=bytes([1])*16
        rows,_,_=self.run_file(bytes(d));self.assertEqual(sum(' = 1234500000' in row for row in rows),512)
        d[1024+31*5+4]=255;self.run_file(bytes(d),refused=True)
    def test_malformed_preflight(self):
        good=sheet()
        for n in (0,33,1023,1535,2047,2560,len(good)-1):self.run_file(good[:n],refused=True)
        self.run_file(good+b'X',refused=True)
        for off,val in ((0,0),(0,33),(2,17),(25,0),(1028,255),(1029,0),(1536+6,255),(1536+9,255),(1549,4),(2048,0x1a),(2053,0x80),(2053,0x2f),(2053,0x0b),(2054,1),(2560,0),(2560,255),(2561,127),(3584,1)):
            d=bytearray(good);d[off]=val;self.run_file(bytes(d),refused=True)
        for value in (b'\xa0\x01\0\0\0\0',b'\xa0'+bytes(4)+b'\x20',bytes(6),b'\x12'+bytes(4)+b'\x20'):
            d=bytearray(good);d[2048:2054]=value;self.run_file(bytes(d),refused=True)
    def test_io_stale_metadata_cancel(self):
        d=dict(originals())['/COSTS.PFS']
        for fault in range(1,8):
            src=self.p/'source';src.write_bytes(d);r=subprocess.run([str(self.exe),str(src),str(fault),'','0','22','4'],check=True,capture_output=True,text=True);self.assertIn('error',r.stderr);self.assertEqual(src.read_bytes(),d)
            if fault in (1,2,3,6,7):self.assertNotIn('|R1',r.stdout)
        for size in (0,1,999999):self.run_file(d,size=size)
        for typ,aux in ((6,4),(22,1),(22,2),(22,22)):self.run_file(d,typ=typ,aux=aux,refused=True)
        rows,counts,_=self.run_file(d,keys='E');self.assertTrue(any(rows));self.assertEqual(counts,(2,2))
    def test_identifier(self):
        from corpus_census import C_SOURCE
        source=self.p/'ident.c';source.write_text(C_SOURCE);libpath=self.p/'ident.so';subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),str(source),'-o',str(libpath)],check=True,capture_output=True)
        identify=ctypes.CDLL(str(libpath)).corpus_ident;identify.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];identify.restype=ctypes.c_char_p
        for typ,aux,dos,expected in ((22,4,0,True),(22,1,0,False),(22,2,0,False),(22,22,0,False),(6,4,0,False),(22,4,1,False)):
            d=sheet();buf=ctypes.create_string_buffer(d);out=ctypes.create_string_buffer(64);identify(b'DATA',typ,aux,buf,len(d),dos,out);self.assertEqual(out.value==b'PFSPLAN',expected)
    def test_cc65_both_cpus(self):
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        bad=bytearray(sheet());bad[3584]=1
        samples=[(sheet(),False),(bytes(bad),True)]+[(d,False) for _,d in originals()]
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1));exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfsplan.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
            for d,refused in samples:self.assertEqual(self.run_file(d,refused=refused,exe=['sim65',str(exe)]),self.run_file(d,refused=refused))

if __name__=='__main__':unittest.main()
