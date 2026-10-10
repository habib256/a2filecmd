"""Actual LISA v4/v5 C: real source files, token boundaries and preserved bytes."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_nexttext import H,NextText,ROOT,big

def lisa4(code=b'\xb3\0',labels=(),tabs=(9,18,40)):
    symbols=b''.join(bytes([len(n)+2])+bytes(ord(c)|128 for c in n)+b'\0' for n in labels)
    h=bytearray(16);h[:2]=b'\x40\xf1';h[2:4]=(16+len(symbols)).to_bytes(2,'little');h[4:6]=len(labels).to_bytes(2,'little');h[6:9]=bytes(tabs);h[9]=0xc0
    return bytes(h)+symbols+code

def real_lisa4():
    from corpus_read import CheckedImage
    p=Path.home()/'.cache/a2fc/cp2/test-files.po'
    if not p.exists():return
    im=CheckedImage(p.read_bytes());key=2
    for name in ('CODE','LISA'):
        e=next(e for e in im.entries(key) if e[1:1+(e[0]&15)].decode()==name);key=int.from_bytes(e[17:19],'little')
    for e in im.entries(key):
        a=int.from_bytes(e[31:33],'little')
        if e[16]==250 and 0x4000<=a<0x6000:yield e[1:1+(e[0]&15)].decode(),a,im.read(e)

class Lisa4(unittest.TestCase):
    run_file=NextText.run_file
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='lisa4-tests-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.executables={}
        exe=cls.p/'lisav4';subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),'-DRT_SOURCE="src/plugins/lisav4.c"',str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True);cls.executables['lisav4']=exe
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def check(self,data,**kw):return self.run_file('lisav4',data,aux=kw.pop('aux',0x50e1),**kw)
    def test_real_files(self):
        found=list(real_lisa4());self.assertEqual(len(found),2)
        for n,a,d in found:
            rows,_,_=self.check(d,filename=n,aux=a);self.assertTrue(any(rows))
    def test_labels_macros_modes_and_comments(self):
        code=big(b'\xfa\0\0\x06\x09\xfa\x01\0\xffcomment')+big(b'\xfc\x01\0\x62\xc1\xa2')+b'\xfa\0\0\xf2\xb3\0'
        rows,_,_=self.check(lisa4(code,['START','ADDR']))
        self.assertEqual([r for r in rows if r],['START    lda      (ADDR),Y              ;comment','         _ADDR    "A"""','START','^2','         dex'])
    def test_long_numbers_strings_and_unary(self):
        nums=(b'\x1a\xff',b'\x1b\xff\xff',b'\x34\xff\xff\xff',b'\x33\0\xff\xff\xff\xff',b'\x35\x56\x34\x12',b'\x33\x01\x78\x56\x34\x12',b'\x36\x12\x34\x56',b'\x33\x03\x03\x01\xAB\xCD',b'\x33\x04\x03ABC',b'\x0f\x13\0\x12',b'\x5e\x14')
        rows,_,_=self.check(lisa4(b''.join(big(b'\x43'+n) for n in nums)+b'\0'))
        self.assertEqual([r.split('=')[1].strip() for r in rows if r],['255','65535','16777215','4294967295','$123456','$12345678','%010101100011010000010010','01ABCD','ABC','-3 + 2','?:4'])
    def test_16bit_symbol_indexes_tabs_and_paging(self):
        labels=['S%03d'%i for i in range(400)]
        code=b''.join(b'\xfa'+i.to_bytes(2,'little') for i in range(400))+b'\0'
        rows,_,_=self.check(lisa4(code,labels));self.assertEqual([r for r in rows if r],labels)
        rows,_,_=self.check(lisa4(code,labels),keys='E');self.assertEqual(len([r for r in rows if r]),21)
        rows,_,_=self.check(lisa4(big(b'\x06\x0e\xfa\0\0')+b'\0',['TARGET'],tabs=(12,22,50)))
        self.assertEqual(rows[0],'            lda       [TARGET],Y')
    def test_malformed_headers_symbols_lines_tokens_and_truncation(self):
        good=lisa4(big(b'\xfa\0\0\x06\x01\x1d\x34\x12')+b'\0',['LABEL'])
        for n in range(len(good)-1):self.check(good[:n],refused=True)
        self.check(good[:-1]) # Physical EOF at a complete record is valid too.
        for pos,val in ((2,0),(3,255),(4,255),(6,0),(7,128),(8,2),(16,1),(18,0),(22,1)):
            bad=bytearray(good);bad[pos]=val;self.check(bytes(bad),refused=True)
        for code in (b'\xfa\xff\xff\0',b'\xfb\0',b'\x80\0',b'\x01\0',big(b'\x06\x10\x11')+b'\0',big(b'\x43\x35\x01')+b'\0',big(b'\x43\x63A')+b'\0',big(b'\x43\x33\x05')+b'\0',b'\0X'):
            self.check(lisa4(code),refused=True)
        for aux in (0x3fff,0x6000):self.check(good,aux=aux,refused=True)
        self.check(lisa4(labels=['TOOLONG']*320),refused=True)
    def test_io_stale_sizes_and_cancel(self):
        data=lisa4(b'\xb3'*600+b'\0')
        for fault in (1,2,3):self.check(data,fault=fault,refused=True)
        for size in (0,1,0xffffff):self.check(data,size=size)
        src=self.p/'source';src.write_bytes(data)
        for fault in (4,5):
            r=subprocess.run([str(self.executables['lisav4']),str(src),str(fault),'','0','250','20705','SAMPLE'],check=True,capture_output=True,text=True)
            self.assertIn('error',r.stderr);self.assertEqual(src.read_bytes(),data)
    def test_all_standard_mnemonics_against_primary_table(self):
        import re
        ref=Path('/tmp/a2fc-next-corpus/reference/Code/LisaAsm.cs')
        if not ref.exists():self.skipTest('primary CiderPress reference unavailable')
        text=ref.read_text();start=text.index('private static readonly string?[] sMnemonics',text.index('class Lisa4'));end=text.index('};',start)
        items=re.findall(r'"([^"\\]*)"|\b(null)\b',re.sub(r'//[^\n]*','',text[start:end]));table=[v if not n else '' for v,n in items]
        code=bytearray();expected=[]
        for m,name in enumerate(table):
            if not m or not name:continue
            expected.append(name.strip())
            if m>=0x90:code.append(m)
            else:
                needs_mode=m<0x12 or (0x30<=m<0x43 and m not in (0x41,0x42))
                code.extend(big(bytes([m])+(b'\0' if needs_mode else b'')+b'\x10'))
        rows,_,_=self.check(lisa4(bytes(code)+b'\0'))
        self.assertEqual([r.strip().split()[0] for r in rows if r],expected)
    def test_all_address_modes_and_coerced_references(self):
        header=['']*9+['(']*4+['[','[','']
        tail=['','','',',X',',X',',X','',',S',',Y','),Y',',X)',')',',S),Y',']','],Y','']
        code=b''.join(big(bytes([6,m,0x1c,0x12])) for m in range(16))+big(b'\x43\x37\xfa\0\0')+big(b'\x43\x38\0\0')+b'\0'
        rows,_,_=self.check(lisa4(code,['ADDR']))
        values=[r.split('lda')[1].strip() for r in rows if 'lda' in r]
        self.assertEqual(values,[header[i]+'$12'+tail[i] for i in range(16)])
        self.assertEqual([r.split('=')[1].strip() for r in rows if '=' in r],['ADDR:A','ADDR:L'])

    def test_cc65_both_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        samples=[lisa4(big(b'\x43\x33\0\xff\xff\xff\xff')+b'\xfa\x8f\x01\0',['S%03d'%i for i in range(400)])]+[d for _,_,d in real_lisa4()]
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1));exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/lisav4.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
            for d in samples:
                src=self.p/'source';src.write_bytes(d);args=[str(src),'0','','0','250','20705','SAMPLE'];expected=subprocess.run([str(self.executables['lisav4'])]+args,check=True,capture_output=True);actual=subprocess.run(['sim65',str(exe)]+args,check=True,capture_output=True,timeout=30)
                self.assertEqual(actual.stdout,expected.stdout);self.assertEqual(actual.stderr,expected.stderr);self.assertEqual(src.read_bytes(),d)

if __name__=='__main__':unittest.main()
