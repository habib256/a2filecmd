"""Run real C viewers on both CPUs; original corpus stays read-only."""
import hashlib, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from test_pfswrite import H, ROOT

SOURCE_ROOT=Path(os.environ.get('A2FC_V1_CORPUS','/tmp/a2fc-v1-corpus'))

def originals(kind):
    seen=set();suffix={'wordperf':'#A00000','mousewr':'#F10000','bsfiler':'#06D3C2','multplan':'.bin'}[kind]
    for p in sorted((SOURCE_ROOT/'extracted').glob('*'+suffix)):
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
    def run_file(self,name,d,fault=0,keys='',size=1,refused=False,exe=None):
        src=self.p/'source';src.write_bytes(d);typ={'wordperf':160,'mousewr':241,'bsfiler':6,'multplan':244}[name]
        cmd=([str(self.executables[name])] if exe is None else exe)+[str(src),str(fault),keys,str(size),str(typ),'0']
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
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            for name in self.executables:
                exe=self.p/(name+'-'+target)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/'+name+'.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
                for label,d in originals(name):self.assertEqual(self.run_file(name,d),self.run_file(name,d,exe=['sim65',str(exe)]),label)

if __name__=='__main__':unittest.main()
