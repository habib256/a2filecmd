"""Run real C viewers on both CPUs; original corpus stays read-only."""
import hashlib, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from test_pfswrite import H, ROOT

SOURCE_ROOT=Path(os.environ.get('A2FC_V1_CORPUS','/tmp/a2fc-v1-corpus'))
MULTIPLAN_ROOT=ROOT/'tools/fixtures/multiplan'

def originals(kind):
    seen=set();suffix={'wordperf':'#A00000','mousewr':'#F10000','bsfiler':'#06D3C2','multplan':'.bin'}[kind]
    paths=sorted((SOURCE_ROOT/'extracted').glob('*'+suffix))
    if kind=='multplan' and not any(p.name.startswith('MP_') for p in paths):
        paths=sorted(MULTIPLAN_ROOT.glob('MP_*.bin'))
    for p in paths:
        d=p.read_bytes();
        if kind=='multplan' and not p.name.startswith('MP_'):continue
        h=hashlib.sha256(d).hexdigest()
        if h not in seen:seen.add(h);yield p.name,d

def mouse(text=b'Hello\r',width=60,version=4):
    h=bytearray(512);h[:5]=b'MW'+bytes([version,0,2]);h[5]=32 if version==1 else 0;h[26]=width
    return bytes(h)+text.ljust(width,b' ')

def filer():
    form=b'\0'*4+b'\x0A\x19Nam\xe5';data=b'Hell\xef'
    h=b''.join(bytes([ord(c)|128]) for c in 'AFILER 1.0')
    h+=b''.join(x.to_bytes(2,'little') for x in (1,2,len(form),len(data),0))
    return h+b'\0\0'+form+data

def filer_long():
    d=bytearray(filer());d[16:18]=(3000).to_bytes(2,'little');return bytes(d[:-5])+b'X'*2999+b'\xD8'

def multiplan_number(exponent):
    pool=b'\0\0\0\0\x08'+bytes([exponent+64])+b'\x12\x34\x50'+bytes(4)
    h=bytearray(666);h[:8]=bytes.fromhex('08E70000D6100100')
    h[250:254]=b'\x01\0\x01\0'
    for off,v in ((652,2),(654,2),(656,2),(658,len(pool)),(660,2+len(pool)),(662,2+len(pool)),(664,3+len(pool))):h[off:off+2]=v.to_bytes(2,'little')
    return bytes(h)+b'\x01\0'+pool

class V1Text(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='v1text-');cls.p=Path(cls.tmp.name)
        harness=H.replace('int main(int argc,char**argv){', r'''static const char* source_path;
static int seek_(FILE* f,long at,int mode){
#ifdef __CC65__
 unsigned char buf[64];FILE* again;unsigned int n;
 if(mode!=SEEK_SET || at<0 || fclose(f))return -1;
 again=fopen(source_path,"rb");if(again!=f)return -1;
 while(at){n=at>64?64:(unsigned int)at;if(fread(buf,1,n,f)!=n)return -1;at-=n;}return 0;
#else
 return fseek(f,at,mode);
#endif
}
int main(int argc,char**argv){''').replace('fault=atoi(argv[2]);','source_path=argv[1];fault=atoi(argv[2]);').replace('api.fopen=opn;', 'api.fseek=seek_;api.fopen=opn;')
        (cls.p/'h.c').write_text(harness);cls.executables={}
        for name in ('wordperf','mousewr','bsfiler','multplan'):
            exe=cls.p/name
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-Wno-deprecated-declarations','-I',str(ROOT),'-DRT_SOURCE="src/plugins/'+name+'.c"',str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True)
            cls.executables[name]=exe
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,name,d,fault=0,keys='',size=1,refused=False,exe=None,typ=None,aux=0):
        src=self.p/'source';src.write_bytes(d)
        if typ is None:typ={'wordperf':160,'mousewr':241,'bsfiler':6,'multplan':244}[name]
        cmd=([str(self.executables[name])] if exe is None else exe)+[str(src),str(fault),keys,str(size),str(typ),str(aux)]
        r=subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=30)
        self.assertEqual(src.read_bytes(),d);parts=r.stderr.rstrip('\n').split(' ',2);note=parts[2] if len(parts)>2 else ''
        rows=[s[1:].rstrip() for s in r.stdout.splitlines() if s.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        elif not fault:self.assertEqual(note,'')
        return rows,parts[:2],note
    def test_independent_text_examples(self):
        rows,_,_=self.run_file('wordperf',b'\xc6\0\x04\xc6\x9dHello\x9c\rworld\x0a\xd2\x01\x04\xff\x0aJNote!\xd2')
        self.assertEqual([r for r in rows if r],['Hello world','[Note!]'])
        rows,_,_=self.run_file('wordperf',b'X\x7F');self.assertIn('X^?',rows)
        for width,version in ((60,1),(65,4),(120,4)):
            rows,_,_=self.run_file('mousewr',mouse(b'Hello\r\x05text',width,version));self.assertEqual([r for r in rows if r],['Hello','^Etext'])
        rows,_,_=self.run_file('bsfiler',filer());self.assertEqual([r for r in rows if r],['Record 1/1','Name: Hello'])
    def test_originals_and_known_records(self):
        for name,minimum in (('wordperf',24),('mousewr',40),('bsfiler',20),('multplan',7)):
            docs=list(originals(name));
            if not docs:self.skipTest('local original corpus not installed')
            self.assertGreaterEqual(len(docs),minimum)
            for label,d in docs:self.run_file(name,d)
        d=next(d for n,d in originals('bsfiler') if '__ANIMALS#' in n)
        rows,_,_=self.run_file('bsfiler',d)
        self.assertIn('Name: Albatross, Wandering',rows);self.assertIn('Heart Chambers: 4',rows);self.assertIn('Weight(lbs.): -999',rows)
        d=next(d for n,d in originals('bsfiler') if '__EXTINCT#' in n)
        rows,_,_=self.run_file('bsfiler',d);self.assertIn('Year: 1627',rows)
    def test_malformed_late_data_before_display(self):
        for name,d in (('wordperf',b'Hello\xc0\0\0\0\0\xc0'),('mousewr',mouse()),('bsfiler',filer())):
            for n in ((0,len(d)-1) if name=='wordperf' else (0,1,len(d)-1)):self.run_file(name,d[:n],refused=True)
            self.run_file(name,d+(b'\xc0' if name=='wordperf' else b'\0'),refused=True)
        self.run_file('wordperf',b'Hello\xd2\x01\x04\xff\x0aJNote',refused=True)
        self.run_file('wordperf',b'Hello\xf8more',refused=True)
        d=bytearray(mouse());d[26]=121;self.run_file('mousewr',bytes(d),refused=True)
        d=bytearray(filer());d[22]=4;self.run_file('bsfiler',bytes(d),refused=True)
        d=bytearray(filer());d[20]=1;self.run_file('bsfiler',bytes(d),refused=True)
    def mouse_bin_cases(self,exe=None):
        for version in (1,4,5):
            for width in (1,60,120):
                data=mouse(b'A',width=width,version=version)
                expected=self.run_file('mousewr',data)[0]
                self.assertEqual(self.run_file('mousewr',data,typ=6,exe=exe)[0],expected)
        docs=list(originals('mousewr'))
        for label,data in docs:
            self.assertEqual(self.run_file('mousewr',data,typ=6,exe=exe),self.run_file('mousewr',data),label)
        if (SOURCE_ROOT/'extracted').exists():self.assertEqual(len(docs),41)
        data=mouse()+mouse()[512:]*99
        for bad in (data[:511],data[:-1],data+b'\0'):
            self.run_file('mousewr',bad,typ=6,exe=exe,refused=True)
        for pos,value in ((0,0),(2,2),(5,1),(26,0),(26,121),(27,1),(len(data)-1,127)):
            bad=bytearray(data);bad[pos]=value
            self.run_file('mousewr',bytes(bad),typ=6,exe=exe,refused=True)
        for typ,aux in ((6,1),(4,0),(0,0)):
            self.run_file('mousewr',data,typ=typ,aux=aux,exe=exe,refused=True)
        for fault in range(1,8):
            rows,_,note=self.run_file('mousewr',data,typ=6,exe=exe,fault=fault)
            self.assertIn('error',note)
            if fault in (1,2,3,6,7):self.assertFalse(any(rows))
        for size in (0,1,0xffffff):self.run_file('mousewr',data,typ=6,exe=exe,size=size)
        rows,counts,note=self.run_file('mousewr',data,typ=6,exe=exe,keys='E')
        self.assertEqual(counts,['2','2']);self.assertEqual(note,'');self.assertEqual(len([r for r in rows if r]),21)

    def test_mousewrite_bin_imports_full_validation(self):self.mouse_bin_cases()
    def test_io_faults_sizes_and_cancel(self):
        for name,d in (('wordperf',b'Hello\x0a'*300),('mousewr',mouse()+mouse()[512:]*99),('bsfiler',next((d for n,d in originals('bsfiler') if '__ANIMALS#' in n), filer_long()))):
            for size in (0,1,999999):self.run_file(name,d,size=size)
            for fault in range(1,8):
                rows,counts,note=self.run_file(name,d,fault=fault)
                self.assertIn('error',note)
                if fault in (1,2,3,6,7):self.assertFalse(any(rows))
            rows,counts,note=self.run_file(name,d,keys='E');self.assertEqual(counts,['2','2']);self.assertEqual(note,'')
    def test_multiplan_cells_pool_and_bcd(self):
        h=bytearray(666);h[:8]=bytes.fromhex('08E70000D6100100')
        h[250:254]=b'\x01\0\x01\0'
        def sheet(pool,pointer=1):
            data=bytearray(h)
            for off,v in ((652,2),(654,2),(656,2),(658,len(pool)),(660,2+len(pool)),(662,2+len(pool)),(664,3+len(pool))):data[off:off+2]=v.to_bytes(2,'little')
            return bytes(data)+pointer.to_bytes(2,'little')+pool
        good=sheet(b'\0\0\0\x40\x05HELLO')
        rows,_,_=self.run_file('multplan',good);self.assertIn('R1C1 = HELLO',rows)
        number=sheet(b'\0\0\0\0\x08\x42\x42'+b'\0'*6)
        rows,_,_=self.run_file('multplan',number);self.assertIn('R1C1 = 42',rows)
        for d in (good[:-1],sheet(b'\0\0\0\x40\x05HELLO',2),sheet(b'\0\0\0\x40\x05HELLO',65535),sheet(b'\0\0\0\0\x08\x42\xFA'+b'\0'*6)):
            self.run_file('multplan',d,refused=True)
        for fault in range(1,8):
            rows,_,note=self.run_file('multplan',good+b'\0'*1024,fault=fault)
            self.assertIn('error',note)
            if fault in (1,2,3,6,7):self.assertFalse(any(rows))
        for label,d in originals('multplan'):
            rows,_,_=self.run_file('multplan',d)
            if 'GRID' in label:self.assertIn('R2C2 = -1.25',rows);self.assertTrue(any(r.startswith('R5C3 = 3 [formula tokens:') for r in rows))
    def test_versioned_multiplan_original_app_fixtures(self):
        manifest=json.loads((ROOT/'docs/corpus/2026-10-27-multiplan-requalification.json').read_text())
        self.assertEqual(len(manifest['files']),7)
        for item in manifest['files']:
            data=(MULTIPLAN_ROOT/item['file']).read_bytes()
            self.assertEqual(len(data),item['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256'])
            rows,_,_=self.run_file('multplan',data)
            for expected in item['expected_cells']:
                if expected.endswith('[formula tokens:'):
                    self.assertTrue(any(r.startswith(expected) for r in rows), (item['file'],expected,rows))
                else:self.assertIn(expected,rows,item['file'])
    def multiplan_bin_cases(self,exe=None):
        docs=list(originals('multplan'))
        for label,data in docs:
            self.assertEqual(self.run_file('multplan',data,typ=6,exe=exe),self.run_file('multplan',data),label)
        if (SOURCE_ROOT/'extracted').exists():self.assertEqual(len(docs),7)
        data=multiplan_number(1)
        for size in (0,1,0xffffff):self.run_file('multplan',data,typ=6,exe=exe,size=size)
        for offset,value in ((0,0),(250,255),(252,255),(652,3),(658,255),(666,2),(667,255),(674,0xfa)):
            bad=bytearray(data);bad[offset]=value
            self.run_file('multplan',bytes(bad),typ=6,exe=exe,refused=True)
        for bad in (data[:665],data[:-1]):self.run_file('multplan',bad,typ=6,exe=exe,refused=True)
        for typ in (4,0,0xf1):self.run_file('multplan',data,typ=typ,exe=exe,refused=True)
        for fault in range(1,8):
            rows,_,note=self.run_file('multplan',data+bytes(1024),typ=6,exe=exe,fault=fault)
            self.assertIn('error',note)
            if fault in (1,2,3,6,7):self.assertFalse(any(rows))

    def test_multiplan_bin_imports_full_validation(self):self.multiplan_bin_cases()
    def multiplan_grid_dimensions(self,exe=None):
        # Independent 2x2 grid: the only number is at R2C2. Moving the
        # saved cursor to R1C1 must not shrink the table to one cell.
        h=bytearray(666);h[:8]=bytes.fromhex('08E70000D6100100')
        h[250:254]=b'\x02\0\x02\0'
        for off,value in ((652,8),(654,8),(656,8),(658,13),(660,21),(662,21),(664,22)):
            h[off:off+2]=value.to_bytes(2,'little')
        data=h+b'\0\0'*3+b'\x01\0'+b'\0\0\0\0\x08\x42\x42'+bytes(6)
        for row,col in ((0,0),(1,1),(254,62)):
            saved=bytearray(data);saved[628:632]=row.to_bytes(2,'little')+col.to_bytes(2,'little')
            rows,counts,_=self.run_file('multplan',saved,exe=exe)
            self.assertEqual([r for r in rows if r],['R2C2 = 42']);self.assertEqual(counts,['2','2'])
        # A cursor that agrees with a damaged header cannot authorize it.
        for row,col in ((0,2),(2,0),(256,2),(2,64),(255,63),(1,1)):
            bad=bytearray(data);bad[250:254]=row.to_bytes(2,'little')+col.to_bytes(2,'little')
            bad[628:632]=bytes(4)
            self.run_file('multplan',bad,exe=exe,refused=True)
        for fault in range(1,8):
            _,_,note=self.run_file('multplan',data,exe=exe,fault=fault)
            self.assertIn('error',note)
    def test_multiplan_grid_is_independent_of_saved_cursor(self):self.multiplan_grid_dimensions()
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            for name in self.executables:
                exe=self.p/(name+'-'+target)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/'+name+'.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
                for label,d in originals(name):self.assertEqual(self.run_file(name,d),self.run_file(name,d,exe=['sim65',str(exe)]),label)
                if name=='mousewr':self.mouse_bin_cases(['sim65',str(exe)])
                if name=='multplan':
                    self.multiplan_grid_dimensions(['sim65',str(exe)])
                    self.multiplan_bin_cases(['sim65',str(exe)])
                    for exp in (-63,-7,-6,0,1,5,14,15,63):
                        d=multiplan_number(exp)
                        self.assertEqual(self.run_file(name,d),self.run_file(name,d,exe=['sim65',str(exe)]))

if __name__=='__main__':unittest.main()
