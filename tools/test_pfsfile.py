"""Actual PFS:File C: reachable records/forms, original bytes and I/O faults."""
import ctypes,hashlib,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_retrotext import HARNESS,ROOT
H=HARNESS.replace('e.size=strtoul(argv[4],0,10);','e.size=strtoul(argv[4],0,10);e.type=atoi(argv[5]);e.aux=atoi(argv[6]);').replace('api.fopen=opn;','api.fseek=seek_;api.fopen=opn;').replace('if(fault==1)return NULL;','if(fault==1 || (fault==7 && opens==2))return NULL;').replace('int main(int argc,char**argv){',r'''
static int seeks;
static int seek_(FILE* f,long o,int w){++seeks;if(fault==6 || (fault==8 && seeks==3))return -1;return fseek(f,o,w);}
int main(int argc,char**argv){''')

def field(x,y,text):
    value=text+(b'\x04' if len(text)%2==0 else b'')+b'\0'
    return (len(value)+4).to_bytes(2,'little')+bytes((x,y))+value

def database(values=None,labels=None):
    if labels is None:labels=[(0,0,b'Name:'),(0,2,b'Amount:')]
    if values is None:values=[[(6,0,b'Alice'),(8,2,b'$10.00')],[(6,0,b'Bob'),(8,2,b'$20.00')]]
    data=bytearray(16384)
    def word(o,v):data[o:o+2]=v.to_bytes(2,'little')
    word(0,127);word(2,127);word(4,1);word(6,len(values));word(8,64 if values else 0);word(10,64+2*(len(values)-1) if values else 0);data[16:22]=b'A2CD00'
    def record(slot,id,prev,next,fields):
        payload=b'\0\0\0\0\x01\0'+id.to_bytes(2,'little')+prev.to_bytes(2,'little')+next.to_bytes(2,'little')+b''.join(field(*f) for f in fields)+b'\0\0'
        assert len(payload)<=1134
        for i in range(0,len(payload),126):
            cell=slot+i//126;part=payload[i:i+126];data[cell*128:cell*128+len(part)]=part
            word(cell*128+126,cell+1 if i+126<len(payload) else 0)
    form=127 if sum(len(field(*f)) for f in labels)+14<=126 else 120
    word(0,form);word(2,form);record(form,0xbd98,0,0,labels)
    for i,v in enumerate(values):record(64+i*2,len(values)-i,64+(i-1)*2 if i else 0,64+(i+1)*2 if i+1<len(values) else 0,v)
    return bytes(data)

def real_files():
    from corpus_read import files
    root=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus'))/'images/productivity/integrated/pfs'
    for path in (root/'PFS_REPORT_hr.dsk',root/'PFS Plan.po'):
        _,entries=files(path.read_bytes())
        for n,t,a,d in entries:
            if t==22 and a==1:yield n,d

class PfsFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pfsfile-tests-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfsfile.c"',str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,d,fault=0,keys='',size=1,typ=22,aux=1,refused=False,exe=None):
        src=self.p/'source';src.write_bytes(d);args=[str(src),str(fault),keys,str(size),str(typ),str(aux)]
        r=subprocess.run(([str(self.exe)] if exe is None else exe)+args,check=True,capture_output=True,text=True,timeout=30)
        self.assertEqual(src.read_bytes(),d);op,cl,note=r.stderr.rstrip('\n').split(' ',2);rows=[s[1:].rstrip() for s in r.stdout.splitlines() if s.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        else:self.assertEqual(note,'',r.stderr)
        return rows,(int(op),int(cl)),note
    def test_named_fields_multiple_records_and_empty_database(self):
        rows,counts,_=self.run_file(database());self.assertEqual([r for r in rows if r],['Record 1/2 (ID 2)','Name: Alice','Amount: $10.00','Record 2/2 (ID 1)','Name: Bob','Amount: $20.00']);self.assertEqual(counts,(2,2))
        rows,_,_=self.run_file(database([]));self.assertEqual([r for r in rows if r],['[0]'])
        # Deleted/unlinked data is read physically but must never become a row.
        d=bytearray(database());d[70*128:70*128+12]=b'DELETED DATA'
        d[64*128+6:64*128+8]=(17).to_bytes(2,'little');d[66*128+6:66*128+8]=(4).to_bytes(2,'little')
        rows,_,_=self.run_file(bytes(d));self.assertNotIn('DELETED', '\n'.join(rows));self.assertIn('Record 1/2 (ID 17)',rows);self.assertIn('Record 2/2 (ID 4)',rows)
    def test_multicell_fields_and_coordinate_fallback(self):
        d=database([[(6,0,b'A'*120+b'\x015Street\x01?City'),(8,2,b'$10.00'),(1,5,b'Other\x02')]])
        rows,_,_=self.run_file(d);text='\n'.join(rows);self.assertIn('  Street',text);self.assertIn('  City',text);self.assertIn('[1,5] Other^B',text)
    def test_real_records_literal_fields_and_order(self):
        originals=list(real_files());self.assertEqual(len(originals),2)
        for n,d in originals:
            rows,_,_=self.run_file(d);headers=[r for r in rows if r.startswith('Record ')]
            self.assertEqual(len(headers),8 if n=='/STAFF.PFS' else 41)
            if n=='/STAFF.PFS':
                self.assertIn('Employee #: A0139',rows);self.assertIn('Name: Woolf, James',rows);self.assertIn('Name: Calvin, Curt',rows)
            else:
                self.assertIn('Expense Category: Utilities',rows);self.assertIn('Pay to: West Coast Gas and Electric',rows);self.assertIn('   44189 S. Main St.',rows);self.assertIn('Amount: $127.30',rows)
    def test_headers_truncation_bad_chain_and_aliases(self):
        good=database()
        for n in (0,127,512,8192,len(good)-1):self.run_file(good[:n],refused=True)
        for off,val in ((0,1),(2,1),(4,2),(6,3),(8,0),(10,64),(16,66),(64*128+4,2),(64*128+10,64),(66*128+8,0),(64*128+126,64),(64*128+126,127),(64*128+126,255)):
            d=bytearray(good);d[off]=val;self.run_file(bytes(d),refused=True)
        self.run_file(good+b'\0',refused=True)
    def test_field_lengths_padding_controls_and_bounds(self):
        good=database()
        for off,val in ((127*128+12,1),(127*128+13,255),(127*128+14,80),(127*128+15,128),(64*128+12,7),(64*128+13,255),(64*128+21,88),(64*128+16,0),(64*128+16,255)):
            d=bytearray(good);d[off]=val;self.run_file(bytes(d),refused=True)
        for text in (b'A\x01',b'A\x01\x7fB',b'A\x04B',b'A\0B',b'\xff'):
            self.run_file(database([[(6,0,text)]]),refused=True)
        labels=[(i,0,b'N:') for i in range(33)];self.run_file(database([],labels),refused=True)
        self.run_file(database([],[(0,0,b'One'),(0,0,b'Two')]),refused=True)
        self.run_file(database([[(6,0,b'A'*980)]]))
        self.run_file(database([[(6,0,b'A'*1000)]]),refused=True)
        self.run_file(database()+bytes(262144-16384))
        self.run_file(bytes(262656),refused=True)
    def test_io_stale_sizes_and_cancel(self):
        d=database()
        for fault in (1,2,3,6,7,8):self.run_file(d,fault=fault,refused=True)
        for fault in (4,5):
            src=self.p/'source';src.write_bytes(d);r=subprocess.run([str(self.exe),str(src),str(fault),'','0','22','1'],check=True,capture_output=True,text=True);self.assertIn('error',r.stderr);self.assertEqual(src.read_bytes(),d)
        for size in (0,1,999999):self.run_file(d,size=size)
        for typ,aux in ((6,1),(22,2),(22,4),(22,22)):self.run_file(d,typ=typ,aux=aux,refused=True)
        rows,counts,_=self.run_file(next(d for n,d in real_files() if n=='/COSTFILE.PFS'),keys='E');self.assertTrue(any(rows));self.assertEqual(counts,(2,2))
    def test_actual_identifier_routes_file_only(self):
        from corpus_census import C_SOURCE
        source=self.p/'ident.c';source.write_text(C_SOURCE);libpath=self.p/'ident.so'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),str(source),'-o',str(libpath)],check=True,capture_output=True)
        identify=ctypes.CDLL(str(libpath)).corpus_ident;identify.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];identify.restype=ctypes.c_char_p
        for typ,aux,dos,expected in ((22,1,0,True),(22,2,0,False),(22,4,0,False),(22,22,0,False),(6,1,0,False),(22,1,1,False)):
            d=database();buf=ctypes.create_string_buffer(d);out=ctypes.create_string_buffer(64);label=identify(b'NO.SUFFIX',typ,aux,buf,len(d),dos,out);self.assertIsNotNone(label);self.assertEqual(out.value==b'PFSFILE',expected)
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        samples=[(d,False) for d in [database(),database([]),database([[(6,0,b'A'*120+b'\x015Street')]])]+[d for _,d in real_files()]]
        shared=bytearray(database());shared[64*128+126:64*128+128]=(68).to_bytes(2,'little');shared[66*128+126:66*128+128]=(68).to_bytes(2,'little')
        samples.append((bytes(shared),True))
        # sim65's stdio has no lseek. Reopen and discard to emulate SEEK_SET,
        # updating the actual decoder FILE; native benches use real ProDOS seeks.
        sh=H.replace('return fseek(f,o,w);', 'if(w!=SEEK_SET || o<0)return -1; {FILE* next=fopen(rt_api.full,"rb");long k;if(!next)return -1;fclose(f);rt_file=next;for(k=0;k<o;++k)if(fgetc(next)==EOF)return -1;}return 0;')
        (self.p/'simh.c').write_text(sh)
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1));exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),'-DRT_SOURCE="src/plugins/pfsfile.c"','-o',str(exe),str(self.p/'simh.c')],check=True,capture_output=True)
            for d,refused in samples:self.assertEqual(self.run_file(d,refused=refused,exe=['sim65',str(exe)]),self.run_file(d,refused=refused))

if __name__=='__main__':unittest.main()
