"""Actual C Magic Window/LISA v3: bounded tokens, real sources, I/O, CPUs."""
import os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_retrotext import HARNESS,ROOT

H=HARNESS.replace('e.size=strtoul(argv[4],0,10);',
 'e.size=strtoul(argv[4],0,10);e.type=atoi(argv[5]);e.aux=atoi(argv[6]);strcpy(e.name,argv[7]);')

def magic(text=b'Hello\r',high=True):
    header=bytearray(256);header[0]=0x8d;header[2]=0xa0 if high else 32
    return bytes(header)+bytes(c|128 if high else c for c in text)

def packed(label):
    chars=[ord(c)&63 for c in label.ljust(8)]
    bits=0
    for c in chars:bits=(bits<<6)|c
    return bits.to_bytes(6,'big')+b'\0\0'

def big(data):return bytes([len(data)+1])+data

def lisa(code=b'\xce\0',labels=()):
    sym=b''.join(packed(s) for s in labels)
    return len(code).to_bytes(2,'little')+len(sym).to_bytes(2,'little')+sym+code

def real_files():
    from corpus_read import CheckedImage,files
    root=Path(os.environ.get('A2FC_NEXT_CORPUS','/tmp/a2fc-next-corpus'))
    path=root/'images/productivity/word_processing/magic_window/MagicWindowIIe.DSK'
    if path.exists():
        _,entries=files(path.read_bytes())
        for n,t,a,d in entries:
            if n.endswith('.MW'):yield 'magwin',n,t,a,d
    path=Path.home()/'.cache/a2fc/cp2/test-files.po'
    if path.exists():
        disk=CheckedImage(path.read_bytes())
        # Select one directory: unrelated resource forks are not needed.
        key=2
        for name in ('CODE','LISA'):
            entry=next(e for e in disk.entries(key) if e[1:1+(e[0]&15)].decode()==name)
            key=int.from_bytes(entry[17:19],'little')
        for e in disk.entries(key):
            n=e[1:1+(e[0]&15)].decode();a=int.from_bytes(e[31:33],'little')
            if e[16]==250 and 0x1000<=a<0x4000:
                yield 'lisav3',n,250,a,disk.read(e)

class NextText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='nexttext-');cls.p=Path(cls.tmp.name)
        (cls.p/'h.c').write_text(H);cls.executables={}
        for name in ('magwin','lisav3'):
            exe=cls.p/name
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                '-DRT_SOURCE="src/plugins/'+name+'.c"',str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True)
            cls.executables[name]=exe
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,name,data,fault=0,keys='',size=0,refused=False,aux=None,filename='SAMPLE'):
        src=self.p/'source';src.write_bytes(data)
        args=[str(src),str(fault),keys,str(size),'6' if name=='magwin' else '250',str(aux if aux is not None else 0x2000),filename[:15]]
        r=subprocess.run([str(self.executables[name])]+args,check=True,capture_output=True,text=True,timeout=10)
        self.assertEqual(src.read_bytes(),data)
        opens,closes,note=r.stderr.rstrip('\n').split(' ',2)
        rows=[r[1:].rstrip() for r in r.stdout.splitlines() if r.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        else:self.assertEqual(note,'',r.stderr)
        return rows,(int(opens),int(closes)),note
    def test_magic_header_ascii_controls_and_limit(self):
        for high in (False,True):
            rows,_,_=self.run_file('magwin',magic(b'Hello\r\x1dBold\x1d\r\x1bA\0Z',high))
            self.assertEqual([r for r in rows if r],['Hello','^]Bold^]','^[A^@Z'])
        for d in (b'',magic()[:255],b'X'+magic()[1:],magic(b'A'*49153)):
            self.run_file('magwin',d,refused=True)
    def test_lisa_symbols_modes_numbers_macros_comments(self):
        code=big(b'\xfa\0\x05\x40\xfa\x01\xffcomment')+big(b'\xfc\x01\x62\xc1\xa2')+b'\xfa\0\xf2\xce\0'
        rows,_,_=self.run_file('lisav3',lisa(code,['START','ADDR']))
        self.assertEqual([r for r in rows if r],[
            'START    lda      (ADDR),Y              ;comment',
            '         /ADDR    "A"""', 'START:', '^2:', '         dex'])
        code=b''.join(big(b'\x34'+v) for v in (b'\x1a\xff',b'\x1b\xff\xff',b'\x1c\xab',b'\x1d\x34\x12',b'\x1e\xa5',b'\x1f\x12\x34',b'\x0f\x03\0\x02',b'\x40\x41'))+b'\0'
        rows,_,_=self.run_file('lisav3',lisa(code))
        self.assertEqual([r.split('=')[1].strip() for r in rows if r],['255','65535','$AB','$1234','%10100101','%0001001000110100','-3 + 2','<0,<1'])
    def test_lisa_all_symbols_both_index_banks_and_paging(self):
        labels=['S%03d'%i for i in range(512)]
        code=b''.join(bytes((250+(i>>8),i&255)) for i in range(512))+b'\0'
        rows,_,_=self.run_file('lisav3',lisa(code,labels))
        self.assertEqual([r for r in rows if r],[s+':' for s in labels])
        rows,_,_=self.run_file('lisav3',lisa(code,labels),keys='E')
        self.assertEqual(len([r for r in rows if r]),21)
    def test_lisa_truncations_tokens_lengths_and_dialect(self):
        good=lisa(big(b'\xfa\0\x05\0\x1d\x34\x12')+b'\0',['LABEL'])
        for n in range(len(good)):self.run_file('lisav3',good[:n],refused=True)
        for code in (b'\xfa',b'\x01',b'\x80',big(b'\x05'),big(b'\x05\x03\x01'),big(b'\x34\x1d\0'),big(b'\x34\x63A'),big(b'\xfa\0\x34\x01'),b'\0\xce'):
            self.run_file('lisav3',lisa(code),refused=True)
        for d in (good+b'X',good[:2]+b'\x01\0'+good[4:],good[:2]+b'\x08\x10'+good[4:]):self.run_file('lisav3',d,refused=True)
        self.run_file('lisav3',good,aux=0x4000,refused=True)
        self.run_file('lisav3',good,filename='ANIX.EQUATES',refused=True)
    def test_io_stale_sizes_and_cancel(self):
        for name,data in (('magwin',magic(b'Hello\r'*150)),('lisav3',lisa(b'\xce'*150+b'\0'))):
            for fault in range(1,6):
                # First-pass failures produce no display; second pass may
                # already have printed validated pages, but must report I/O.
                rows,_,note=self.run_file(name,data,fault=fault,refused=fault<=3) if fault<=3 else self.fault_result(name,data,fault)
                self.assertIn('error',note)
            for size in (0,1,16777215):self.run_file(name,data,size=size)
            rows,_,_=self.run_file(name,data,keys='E');self.assertEqual(len([r for r in rows if r]),21)
    def fault_result(self,name,data,fault):
        # Permit expected error without permitting a successful reader result.
        src=self.p/'source';src.write_bytes(data)
        r=subprocess.run([str(self.executables[name]),str(src),str(fault),'','0','6' if name=='magwin' else '250','8192','SAMPLE'],capture_output=True,text=True,check=True)
        self.assertEqual(src.read_bytes(),data);a,b,n=r.stderr.rstrip('\n').split(' ',2)
        return [],(int(a),int(b)),n
    def test_real_files(self):
        found=list(real_files())
        if not found:self.skipTest('next text corpus unavailable')
        for name,n,t,a,d in found:
            rows,_,_=self.run_file(name,d,aux=a,filename=n,refused=n=='ANIX.EQUATES')
            if n!='ANIX.EQUATES':self.assertTrue(any(rows))
        for kind,expected in (('magwin',6),('lisav3',3)):
            count=sum(r==kind for r,_,_,_,_ in found)
            if count:self.assertEqual(count,expected)
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65/sim65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        samples=[('lisav3',lisa(b'\xfb\xff\0',['S%03d'%i for i in range(512)]),8192),('magwin',magic(b'Hello\r\x1bA'),8192),('lisav3',lisa(big(b'\xfa\0\x34\x1b\xff\xff')+b'\xce\0',['LABEL']),8192)]
        for name,n,t,a,d in real_files():
            if n!='ANIX.EQUATES':samples.append((name,d,a))
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            for name in ('magwin','lisav3'):
                exe=self.p/(target+name)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/'+name+'.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
                for format_,d,a in samples:
                    if format_!=name:continue
                    src=self.p/'source';src.write_bytes(d);args=[str(src),'0','','0','6' if name=='magwin' else '250',str(a),'SAMPLE']
                    expected=subprocess.run([str(self.executables[name])]+args,check=True,capture_output=True)
                    actual=subprocess.run(['sim65',str(exe)]+args,check=True,capture_output=True,timeout=30)
                    self.assertEqual(actual.stdout,expected.stdout);self.assertEqual(actual.stderr,expected.stderr);self.assertEqual(src.read_bytes(),d)

if __name__=='__main__':unittest.main()
