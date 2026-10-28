"""Real detector stages: shared Merlin fallback after concrete formats."""
import ctypes
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_names as N
from test_dos_names import V1, FORMATS, high
from test_six_plugins import PREFIX, ROOT
from corpus_census import C_SOURCE

H = PREFIX + r'''
#include "src/a2fc_plugin.h"
#include "src/plugins/id_context.h"
unsigned char host_id_sample[512];
unsigned char __fastcall__ id_detect(const struct A2fcApi*);
unsigned char __fastcall__ id_formats(const struct A2fcApi*);
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Entry entry;static struct Panel panels[2];
 static unsigned char active,scratch[512];static char context[81],input[64],note[80];
 FILE* source;unsigned int got;unsigned long total;unsigned char next,bad;
 source=fopen(argv[1],"rb");if(!source)return 2;
 got=fread(host_id_sample,1,512,source);total=got;
 while((next=ferror(source))==0){unsigned int more=fread(scratch,1,512,source);total+=more;if(!more)break;}
 if(next || ferror(source) || fclose(source))return 3;
 strcpy(entry.name,argv[7]);entry.type=atoi(argv[2]);entry.size=strtoul(argv[5],0,10);entry.mdate=783;entry.aux=atoi(argv[8]);
 panels[0].fs=atoi(argv[3]);api.panels=panels;api.active=&active;api.selected=&entry;
 api.copy_buf=scratch;api.other_full=context;api.input=input;api.note=note;
 api.strcpy=strcpy;api.sprintf=sprintf;api.arg=atoi(argv[4]);
 memset(context+10,' ',30);id_context(&api,got,total,entry.aux,entry.type);
 bad=atoi(argv[6]);if(bad==1)context[48]^=1;
 if(bad==2){context[0]=1;context[1]=3;}if(bad==3)context[42]=5;
 if(bad==4)context[8]^=1;
 if(bad==5){context[2]=context[3]=context[4]=context[5]=0;}
 next=id_detect(&api);
 if(next && context[42]==3)next=id_formats(&api);
 if(next && context[42]==4)next=id_detect(&api);
 if(next && context[42]!=1)abort();
 printf("%s|%s\n",input[0]?input:"FALLBACK",note);return 0;
}
'''

class MerlinIdentification(unittest.TestCase):
    compile = N.Names.__dict__['compile']

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='merlin-ident-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'h.c';cls.h.write_text(H);cls.v1=cls.p/'v1.c';cls.v1.write_text(V1)
        cls.fm=cls.p/'formats.c';cls.fm.write_text(FORMATS);cls.exe=cls.p/'host';cls.compile(cls.exe)
        source=cls.p/'classifier.c';source.write_text(C_SOURCE);lib=cls.p/'classifier.so'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),str(source),'-o',str(lib)],check=True,capture_output=True)
        cls.lib=ctypes.CDLL(str(lib));cls.identify=cls.lib.corpus_ident
        cls.identify.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p]
        cls.identify.restype=ctypes.c_char_p

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def check(self,data,expected,typ=4,size=1,arg=13,bad=0,exe=None,name='SOURCE',aux=0):
        source=self.p/'source';source.write_bytes(data)
        cmd=[str(self.exe)] if exe is None else ['sim65',str(exe)]
        result=subprocess.run(cmd+[str(source),str(typ),'0',str(arg),str(size),str(bad),name,str(aux)],check=True,capture_output=True,text=True)
        self.assertEqual(source.read_bytes(),data)
        if bad:self.assertTrue(result.stdout.startswith('FALLBACK|Invalid'),result.stdout)
        else:self.assertEqual(result.stdout,expected+'|\n')

    def test_return_runs_sys_and_other_keys_still_read(self):
        code=bytes([0x4C,0,0x20])+bytes(64)
        self.check(code,'RUN',typ=255,arg=ord('O'),size=len(code),name='PROG.SYSTEM')
        for arg in (ord('I'),13):self.check(code,'FALLBACK',typ=255,arg=arg,size=len(code),name='PROG.SYSTEM')
        # BIN keeps its content routing on Return.
        self.check(code,'FALLBACK',typ=6,arg=ord('O'),size=len(code),name='PROG')

    def basint_cases(self,exe=None):
        # Return runs a ProDOS BAS or INT; I and T-like keys still read it,
        # and source typed INT keeps its reader.
        bas=bytes((0x0A,8,10,0,0xBA,0x22,0x41,0x22,0,0,0))
        for typ,data in ((252,bas),(250,bytes(32)),(252,b'')):
            self.check(data,'RUN',typ=typ,arg=ord('O'),size=len(data),name='PROG',exe=exe)
            for arg in (ord('I'),13):self.check(data,'FALLBACK',typ=typ,arg=arg,size=len(data),name='PROG',exe=exe)
        self.check(bytes((5,10,0,65,0)),'SCASM',typ=250,arg=ord('O'),size=5,name='SOURCE',exe=exe)
        merlin=high(b'*Shared source\rLABEL LDA #0\r STA $300\r RTS\r')
        self.check(merlin,'MERLIN',typ=250,arg=ord('O'),size=len(merlin),name='T.S',exe=exe)

    def lisa4_cases(self,exe=None):
        from test_lisa4 import lisa4,real_lisa4
        sources=[('SOURCE.A',0x50e1,lisa4())]+list(real_lisa4())
        for name,aux,data in sources:
            for size in (0,1,0xffffff):
                for arg in (13,ord('I'),ord('O')):
                    self.check(data,'LISAV4',typ=250,aux=aux,size=size,arg=arg,name=name,exe=exe)
        good=lisa4()
        for aux in (0,0x3fff,0x6000):
            self.check(good,'RUN',typ=250,aux=aux,arg=ord('O'),exe=exe)
            self.check(good,'FALLBACK',typ=250,aux=aux,arg=ord('I'),exe=exe)
        for offset,value in ((2,0),(3,255),(6,0),(7,1),(8,2)):
            bad=bytearray(good);bad[offset]=value
            self.check(bytes(bad),'RUN',typ=250,aux=0x50e1,arg=ord('O'),exe=exe)
            self.check(bytes(bad),'FALLBACK',typ=250,aux=0x50e1,arg=ord('I'),exe=exe)

    def test_lisa4_sources_precede_integer_basic_execution(self):self.lisa4_cases()

    def test_return_runs_bas_and_int(self):self.basint_cases()

    def cases(self,exe=None):
        body=high(b'*Shared source\rLABEL LDA #0\r STA $300\r RTS\r')
        for size in (0,1,0xffffff):
            for arg in (13,ord('I'),ord('O')):self.check(body,'MERLIN',size=size,arg=arg,exe=exe)
        for b in (b'',b'ordinary text\r',high(b' LDA #0\r STA $300\r'),
                  high(b'* LDA\r* STA\r* RTS\r'),high(b' LDA #0\r STA $300\r RTS'),body+b'\x01'):
            self.check(b,'FALLBACK',exe=exe)
        for typ in (0,250):self.check(body,'FALLBACK',typ=typ,exe=exe)
        # A BIN at 0 of high-bit text is a Bank Street Writer document, as OPEN had it.
        self.check(body,'DOCVIEW',typ=6,exe=exe)
        self.check(high(b'.lm2\r LDA #0\r STA $300\r RTS\r'),'APPLEWR',exe=exe)
        for bad in (1,2,3,4,5):self.check(body,'',bad=bad,exe=exe)
        # The third statement cut by the 512-byte sample must not count.
        prefix=high(b' LDA #0\r STA $300\r')
        self.check(prefix+high(b'*'+b'X'*(507-len(prefix))+b'\r RTS\r'),'FALLBACK',exe=exe)

    def test_real_stages_boundaries_priority_and_context(self):self.cases()

    def visicalc_cases(self,exe=None):
        plain=b'>L40:1140\r>A1:@SUM(B40...L40)\r'
        double=b'>BJ90:"All rights reserved.\r>BK69:1\r'
        for data in (plain,high(plain),bytes(c|128 if i%2 else c for i,c in enumerate(plain)),double,high(double),bytes(c|128 if i%2 else c for i,c in enumerate(double))):
            for arg in (13,ord('I'),ord('O')):
                self.check(data,'VISICALC',arg=arg,exe=exe)
            for bad in (1,2,3,4,5):self.check(data,'',bad=bad,exe=exe)
        for data in (b'> a quoted line\r',b'>A?:not a row\r',b'>@1:not a column\r',b'>A1',b'>AAx:bad row\r',b'>A@1:bad column\r',b'>AAA1:too many letters\r'):
            self.check(data,'FALLBACK',exe=exe)

    def test_visicalc_high_bit_in_real_stages(self):self.visicalc_cases()

    def originals(self,exe=None):
        from legacy_corpus import dos_files
        p=Path.home()/'.cache/a2fc/asimov_corpus/raw/images/programming/assembler/merlin/MERLIN-8_DOS33.dsk'
        if not p.exists():self.skipTest('local Merlin corpus unavailable')
        original=p.read_bytes();count=0
        for name,typ,aux,data in dos_files(original):
            if typ!=4:continue
            expected='FALLBACK' if name=='PI.NAMES' else 'MERLIN'
            with self.subTest(name=name):self.check(data,expected,exe=exe,name=N.display_name(name))
            count+=1
        self.assertEqual(count,9);self.assertEqual(p.read_bytes(),original)

    def test_original_sources_as_prodos_txt(self):self.originals()

    def test_host_classifier_matches_actual_stages(self):
        for data,typ,expected in [(high(b' LDA #0\r STA $300\r RTS\r'),4,'MERLIN'),
                                  (high(b' LDA #0\r STA $300\r'),4,'TEXT'),
                                  (high(b'.lm2\r LDA #0\r STA $300\r RTS\r'),4,'APPLEWR')]:
            raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'SOURCE',typ,0,raw,len(data),0,out))
            self.assertEqual(out.value.decode(),expected)

    def printshop_cases(self,exe=None):
        from test_printshop_extras import font,font5
        for typ,aux,data,expected in ((6,0x6000,font(prefix=0),'PSFONT'),(6,0x5ff4,font(),'PSFONT'),
                                      (0xf5,0x1000,font5(),'PSFONT'),(0xf5,0x2000,bytes(264),'PSBORDER'),
                                      (6,0x4800,bytes(144),'PSBORDER'),(6,0x7800,bytes(148),'PSBORDER')):
            for size in (0,1,0xffffff):
                for arg in (13,ord('I'),ord('O')):self.check(data,expected,typ=typ,aux=aux,exe=exe,size=size,arg=arg)
            self.check(data,'FALLBACK',typ=typ,aux=aux+1,exe=exe)
            self.check(data[:-1],'FALLBACK',typ=typ,aux=aux,exe=exe)
            raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'SOURCE',typ,aux,raw,len(data),0,out))
            self.assertEqual(out.value.decode(),expected)
        for data,typ,aux,start,count in ((font(),6,0x5ff4,12,59),(font5(),0xf5,0x1000,12,95)):
            for pos in (start+count-1,start+2*count-1,start+4*count-1):
                bad=bytearray(data);bad[pos]=255
                self.check(bytes(bad),'FALLBACK',typ=typ,aux=aux,exe=exe)
        for length in (0,143,145,147,149,264,65536+144):
            self.check(bytes(length),'FALLBACK',typ=6,aux=0x4800,exe=exe)

    def test_renamed_printshop_content_and_typed_borders(self):self.printshop_cases()

    def movie_cases(self,exe=None):
        from test_v1media import movie
        def cmd(tag,body=b''):return bytes([tag])+len(body).to_bytes(2,'little')+body
        # A short legal plane exposes the second header in the sample.
        short=cmd(1,bytes(256))+cmd(2,bytes(2))+cmd(3,bytes(2))+cmd(6)+cmd(5,b'\x30\xc0')+cmd(0)+cmd(7)
        for data in (movie(),short):
            for aux in (0,0x6000):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):
                        self.check(data,'MVMOVIE',typ=6,aux=aux,size=size,arg=arg,exe=exe,name='RENAMED')
            raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'RENAMED',6,0x6000,raw,len(data),0,out))
            self.assertEqual(out.value,b'MVMOVIE')
            for typ,aux in ((4,0x6000),(6,0x2000)):
                self.check(data,'FALLBACK',typ=typ,aux=aux,exe=exe)
        for pos,value in ((0,0),(2,2),(259,3),(260,1),(263,255),(264,2),(265,1),(268,255)):
            bad=bytearray(short);bad[pos]=value
            self.check(bytes(bad),'FALLBACK',typ=6,aux=0x6000,exe=exe,name='BAD.MVM')
        for pos in (262,267):
            shifted=bytearray(short);shifted[pos]=255
            self.check(bytes(shifted),'MVMOVIE',typ=6,aux=0x6000,exe=exe)
        for data in (movie()[:263],short[:-1],movie()+bytes(65536)):
            self.check(data,'FALLBACK',typ=6,aux=0x6000,exe=exe)
        cache=Path.home()/'.cache/a2fc/moviemaker/out';seen=set()
        import hashlib
        for p in cache.rglob('*.MVM.bin'):
            data=p.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if digest in seen or data[:3]!=b'\x01\x00\x01':continue
            seen.add(digest)
            self.check(data,'MVMOVIE',typ=6,aux=0x6000,exe=exe,name='RENAMED')
            self.check(data,'MVMOVIE',typ=6,aux=0,exe=exe,name='IMPORTED')
            raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(data),0,out));self.assertEqual(out.value,b'MVMOVIE')
            self.assertEqual(p.read_bytes(),data)
        if cache.exists():self.assertEqual(len(seen),13)

    def test_renamed_movie_headers_actual_eof_and_originals(self):self.movie_cases()

    def pcs_cases(self,exe=None):
        from test_v1media import pcs,pcs_many,CORPUS
        data=pcs()
        for size in (0,1,0xffffff):
            for arg in (13,ord('I'),ord('O')):
                self.check(data,'PCSVW',typ=6,aux=0x4000,size=size,arg=arg,exe=exe)
        for pos,value in ((28,0),(28,255),(29,8),(30,0),(30,11),(31,1),(31,18),(32,2),(32,65),(33,154),(37,192)):
            bad=bytearray(data);bad[pos]=value
            self.check(bytes(bad),'FALLBACK',typ=6,aux=0x4000,exe=exe)
        for body in (data[:29],data[:40],data[:-1]):
            self.check(body,'FALLBACK',typ=6,aux=0x4000,exe=exe)
        for typ,aux in ((4,0x4000),(6,0),(6,0x2000)):
            self.check(data,'FALLBACK',typ=typ,aux=aux,exe=exe)
        # 255 object lengths must be accumulated without an 8-bit wrap.
        many=bytes(28)+bytes([255])+bytes([255])*255+bytes(65025)+bytes(66)
        self.check(many,'FALLBACK',typ=6,aux=0x4000,exe=exe)
        self.check(pcs_many(),'PCSVW',typ=6,aux=0x4000,exe=exe)
        # A bad additional sampled object must not hide behind a valid first.
        bad=bytearray(pcs_many());bad[284+9]=0
        self.check(bytes(bad),'FALLBACK',typ=6,aux=0x4000,exe=exe)
        originals=list((CORPUS/'extracted').glob('*.PB#064000'))
        for p in originals:
            body=p.read_bytes()
            self.check(body,'PCSVW',typ=6,aux=0x4000,exe=exe)
            raw=ctypes.create_string_buffer(body);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'SOURCE',6,0x4000,raw,len(body),0,out))
            self.assertEqual(out.value,b'PCSVW');self.assertEqual(p.read_bytes(),body)
        if (CORPUS/'extracted').exists():self.assertEqual(len(originals),6)

    def test_renamed_pcs_objects_metadata_eof_and_originals(self):self.pcs_cases()

    def dpc_cases(self,exe=None):
        from test_v1media import CORPUS
        data=bytes([0x20,0x81,0x18,0x30,0xa2,0x2f,0xbf,0])
        for size in (0,1,0xffffff):
            for arg in (13,ord('I'),ord('O')):
                self.check(data,'DGMAGI',typ=6,aux=0x4000,size=size,arg=arg,exe=exe)
        for body in (data[:-1],data[:3],data+b'\x01',data[:4]+b'\x70\0\0\0',
                     data[:4]+b'\xa2\x30\0\0',data[:4]+b'\xa2\x2f\xc0\0',
                     b'\x20\xa2\x2f\0\0',b'\x48'+data,b'\x61\0'+data,
                     b'\x30\x1f'+data,b'\x30\x80'+data):
            # Some malformed DPC prefixes can still be GMAGIC candidates;
            # full reader validation owns the final decision.
            raw=ctypes.create_string_buffer(body);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'SOURCE',6,0x4000,raw,len(body),0,out))
            self.assertNotEqual(out.value,b'DGMAGI')
            self.check(body,'GMAGIC' if out.value==b'GMAGIC' else 'FALLBACK',typ=6,aux=0x4000,exe=exe)
        for typ,aux in ((4,0x4000),(6,0),(6,0x2000)):
            self.check(data,'FALLBACK',typ=typ,aux=aux,exe=exe)
        narrow=b'\x20\x80\0\0\xa0\x10\x10\0'
        self.check(narrow,'GMAGIC',typ=6,aux=0x4000,exe=exe)
        # A final command crossing the sample boundary is deferred, while
        # actual EOF without a terminator or beyond the supported limit fails.
        prefix=data[:-1]+b'\x20'*503
        self.check(prefix+b'\x81\x18\x30\0','DGMAGI',typ=6,aux=0x4000,exe=exe)
        self.check((prefix+b'\x81\x18\x30\0')[:512],'FALLBACK',typ=6,aux=0x4000,exe=exe)
        self.check(data+bytes(65536),'FALLBACK',typ=6,aux=0x4000,exe=exe)
        p=CORPUS/'pal-no-text.dpc'
        if p.exists():
            body=p.read_bytes();self.check(body,'DGMAGI',typ=6,aux=0x4000,exe=exe)
            self.assertEqual(p.read_bytes(),body)

    def test_renamed_dpc_commands_width_ambiguity_and_original(self):self.dpc_cases()

    def multiscr_cases(self,exe=None):
        old=b'\x80\x19\x01\0\x01\0\xb1\xe2\x02'+bytes(27)+b'\x02Hello\r'
        new=b'\x80\x19\x01\0\x01\0\x19\x01\x86\x19\x0a\x01\x14\x14'+bytes(280)+b'\x02Hello\r'
        for data in (old,new):
            for typ in (4,11,6):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):
                        self.check(data,'MULTISCR',typ=typ,aux=0x8000,size=size,arg=arg,exe=exe)
            for pos in (0,1,4,5,6,7,8):
                bad=bytearray(data);bad[pos]^=0x10
                self.check(bytes(bad),'FALLBACK',typ=6,exe=exe)
            for typ in (0,250):self.check(data,'FALLBACK',typ=typ,exe=exe)
            self.check(data[:8],'FALLBACK',typ=6,exe=exe)
        root=Path(os.environ.get('A2FC_WORDPRO_CORPUS','/tmp/a2fc-wordpro-corpus'))/'extracted'
        originals=[p for p in root.glob('*') if p.is_file() and p.read_bytes()[:2]==b'\x80\x19']
        for p in originals:
            data=p.read_bytes();self.check(data,'MULTISCR',typ=6,exe=exe)
            raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(data),0,out))
            self.assertEqual(out.value,b'MULTISCR');self.assertEqual(p.read_bytes(),data)
        if root.exists():self.assertEqual(len(originals),12)

    def test_imported_multiscribe_bin_matches_txt_wpf(self):self.multiscr_cases()

    def mouse_bin_cases(self,exe=None):
        from test_v1text import mouse,originals,SOURCE_ROOT
        for version in (1,4,5):
            for width in (1,60,120):
                data=mouse(width=width,version=version)
                for typ in (6,0xf1):
                    for size in (0,1,0xffffff):
                        for arg in (13,ord('I'),ord('O')):
                            self.check(data,'MOUSEWR',typ=typ,size=size,arg=arg,exe=exe)
        data=mouse()
        for pos,value in ((0,0),(1,0),(2,2),(3,1),(4,0),(5,1),(26,0),(26,121),(27,1)):
            bad=bytearray(data);bad[pos]=value
            for typ in (6,0xf1):self.check(bytes(bad),'FALLBACK',typ=typ,exe=exe)
        self.check(data,'FALLBACK',typ=6,aux=1,exe=exe)
        self.check(data[:27],'FALLBACK',typ=6,exe=exe)
        for typ in (0,4,11):self.check(data,'FALLBACK',typ=typ,exe=exe)
        docs=list(originals('mousewr'))
        for label,body in docs:
            self.check(body,'MOUSEWR',typ=6,exe=exe)
            raw=ctypes.create_string_buffer(body);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(body),0,out));self.assertEqual(out.value,b'MOUSEWR')
        if (SOURCE_ROOT/'extracted').exists():self.assertEqual(len(docs),41)

    def test_mousewrite_bin_header_metadata_and_originals(self):self.mouse_bin_cases()

    def multiplan_bin_cases(self,exe=None):
        from test_v1text import multiplan_number,originals,SOURCE_ROOT
        data=multiplan_number(1)
        for typ in (6,0xf4):
            for size in (0,1,0xffffff):
                for arg in (13,ord('I'),ord('O')):
                    self.check(data,'MULTPLAN',typ=typ,size=size,arg=arg,exe=exe)
            for pos in range(8):
                bad=bytearray(data);bad[pos]^=0x80
                # F4 retains the existing LISA v2 candidate for its length
                # field; BIN must not acquire that metadata-only fallback.
                expected='LISAV2' if typ==0xf4 and pos in (2,3) else 'FALLBACK'
                self.check(bytes(bad),expected,typ=typ,exe=exe)
        for typ in (0,4,11):self.check(data,'FALLBACK',typ=typ,exe=exe)
        self.check(data[:7],'FALLBACK',typ=6,exe=exe)
        docs=list(originals('multplan'))
        for label,body in docs:
            self.check(body,'MULTPLAN',typ=6,exe=exe)
            raw=ctypes.create_string_buffer(body);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(body),0,out));self.assertEqual(out.value,b'MULTPLAN')
        if (SOURCE_ROOT/'extracted').exists():self.assertEqual(len(docs),7)

    def test_multiplan_bin_signature_and_originals(self):self.multiplan_bin_cases()

    def lisa_bin_cases(self,exe=None):
        from test_nexttext import lisa,big,real_files
        good=lisa(big(b'\xfa\0\x05\0\x1d\x34\x12')+b'\0',['LABEL'])
        for typ in (6,0xfa):
            for aux in (0x1000,0x2000,0x3fff):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):
                        self.check(good,'LISAV3',typ=typ,aux=aux,size=size,arg=arg,exe=exe)
            for aux in (0,0xfff,0x4000,0xffff):self.check(good,'FALLBACK',typ=typ,aux=aux,exe=exe)
            self.check(good,'FALLBACK',typ=typ,aux=0x2000,name='ANIX.EQUATES',exe=exe)
        for typ in (0,4,11):self.check(good,'FALLBACK',typ=typ,aux=0x2000,exe=exe)
        for data in (good[:-1],good+b'X',b'\0\0'+good[2:],good[:2]+b'\x01\0'+good[4:],good[:2]+b'\x08\x10'+good[4:]):
            self.check(data,'FALLBACK',typ=6,aux=0x2000,exe=exe)
        found=0
        for kind,name,typ,aux,data in real_files():
            if kind!='lisav3':continue
            expected='FALLBACK' if name=='ANIX.EQUATES' else 'LISAV3'
            self.check(data,expected,typ=6,aux=aux,name=name,exe=exe)
            if expected=='LISAV3':
                found+=1;raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
                self.assertTrue(self.identify(name.encode(),6,aux,raw,len(data),0,out));self.assertEqual(out.value,b'LISAV3')
        if found:self.assertEqual(found,2)

    def test_lisa_bin_lengths_metadata_and_originals(self):self.lisa_bin_cases()

    def sc_bin_cases(self,exe=None):
        from test_retrotext import sc_line,sc_originals
        good=sc_line(100,b'\x89LDA\x83#0')+sc_line(65535,b'\xc0\x05*')
        for typ in (6,0xfa):
            for aux in (0,0x800,0x6000):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):
                        self.check(good,'SCASM',typ=typ,aux=aux,size=size,arg=arg,exe=exe,name='IMPORTED')
        for typ in (0,4,11):self.check(good,'FALLBACK',typ=typ,exe=exe)
        for data in (good[:3],b'\x03'+good[1:],good[:len(sc_line(100,b'\x89LDA\x83#0'))-1],sc_line(1,b'\xc0'),sc_line(1,b'\xc0\xff\0'),sc_line(1,b'\xc1'),sc_line(1,b'\0X')):
            self.check(data,'FALLBACK',typ=6,exe=exe)
        self.check(sc_line(1,b'A'*251),'SCASM',typ=6,exe=exe)
        # Every whole line of the sample must be source: a cut last line only
        # when the 512-byte sample is full, numbers strictly rising.
        self.check(good[:-1],'FALLBACK',typ=6,exe=exe)
        self.check(sc_line(100,b'\x89LDA')+bytes((150,1,2,3,4,5)),'FALLBACK',typ=6,exe=exe)
        self.check(sc_line(100,b'\x89LDA')+sc_line(100,b'\x89RTS'),'FALLBACK',typ=6,exe=exe)
        self.check(sc_line(100,b'\x89LDA')+sc_line(90,b'\x89RTS'),'FALLBACK',typ=6,exe=exe)
        long=b''.join(sc_line(10*i+10,b'\x89LDA\x83#0 '+b'*'*21) for i in range(40))
        self.check(long,'SCASM',typ=6,exe=exe);self.check(long,'SCASM',typ=0xfa,exe=exe)
        self.check(long[:511],'FALLBACK',typ=6,exe=exe)
        save=sc_line(1000,b'.LIF')+sc_line(1010,b'*\xc0\x06\x08SAVE S.X')+sc_line(1020,b'*\xc0\x21-')
        for typ in (6,0xfa):self.check(save,'SCASM',typ=typ,arg=ord('O'),exe=exe)
        self.check(sc_line(1000,b'.LIF')+sc_line(1010,b'*\xc0\x06\0'),'FALLBACK',typ=6,exe=exe)
        originals=list(sc_originals())
        if originals:self.assertEqual(len(originals),12)
        for name,source in originals:
            self.check(source,'SCASM',typ=6,exe=exe,name='IMPORTED')
            raw=ctypes.create_string_buffer(source);out=ctypes.create_string_buffer(64)
            self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(source),0,out));self.assertEqual(out.value,b'SCASM')

    def test_sc_bin_first_record_metadata_and_original(self):self.sc_bin_cases()

    def arlequin_bin_cases(self,exe=None):
        import random,arlequin_ref as ref
        rng=random.Random(4);data=ref.encode(9,ref.random_rows(9,81,rng),rng)
        for typ in (6,0xf8):
            for aux in (0,0x385):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):self.check(data,'ARLEQUIN',typ=typ,aux=aux,size=size,arg=arg,exe=exe,name='IMPORTED')
        for typ in (0,4,11):self.check(data,'FALLBACK',typ=typ,exe=exe)
        for body in (data[:3],data[:2]+b'xx'+data[4:]):self.check(body,'FALLBACK',typ=6,exe=exe)
        raw=ctypes.create_string_buffer(data);out=ctypes.create_string_buffer(64)
        self.assertTrue(self.identify(b'IMPORTED',6,0,raw,len(data),0,out));self.assertEqual(out.value,b'ARLEQUIN')

    def test_arlequin_bin_signature_and_metadata(self):self.arlequin_bin_cases()

    def macpaint_cases(self,exe=None):
        import macpaint_ref as ref
        header=bytearray(ref.pack([bytes(72)]*720,macbinary=True)[:640])
        header[83:87]=(1952).to_bytes(4,'big')
        data=bytes(header)+b'\xB9\0'*720
        self.assertEqual(len(data),2080)
        for typ in (0,6):
            for aux in (0,0x2000):
                for size in (0,1,0xffffff):
                    for arg in (13,ord('I'),ord('O')):
                        self.check(data,'MACPAINT',typ=typ,aux=aux,size=size,arg=arg,exe=exe,name='RENAMED')
            # A concrete container wins the generic 8K/16K classification.
            for size in (8192,16384):self.check(data+bytes(size-len(data)),'MACPAINT',typ=typ,exe=exe)
            for body in (data[:127],data[:-1],bytes([1])+data[1:],data[:65]+b'XXXX'+data[69:]):
                self.check(body,'FALLBACK',typ=typ,exe=exe)
        for typ in (4,8,0xff):self.check(data,'FALLBACK',typ=typ,exe=exe)
        raw=ref.pack([bytes(72)]*720)
        self.check(raw,'MACPAINT',typ=0,exe=exe,name='PICTURE.PNTG')
        self.check(raw,'FALLBACK',typ=0,exe=exe,name='RENAMED')
        for name in ('.PNTG','PICTURE.PNTGX','PICTURE.PNT'):self.check(raw,'FALLBACK',typ=0,exe=exe,name=name)
        for body in (data,raw):
            for name in ('RENAMED','PICTURE.PNTG'):
                expected='MACPAINT' if body==data or name.endswith('.PNTG') else 'HEX'
                buf=ctypes.create_string_buffer(body);out=ctypes.create_string_buffer(64)
                self.assertTrue(self.identify(name.encode(),0,0,buf,len(body),0,out));self.assertEqual(out.value.decode(),expected)

    def test_macbinary_content_and_pntg_suffix(self):self.macpaint_cases()

    def open_metadata_cases(self,exe=None):
        # OPEN's metadata rules in IDFORMATS, before any content probe.
        hi=lambda t:bytes(c|0x80 for c in t);gm=bytes.fromhex('2280000AA1170A25');O=ord('O')
        for name,typ,aux,data,expected in (
            ('PIC',6,0x2000,gm+bytes(8184),'IMAGE'),('PIC',6,0,hi(b' LDA #0\r')*1023,'IMAGE'),
            ('PIC',6,0xE000,bytes(16376),'IMAGE'),('PIC',6,0x2000,bytes(8183),'FALLBACK'),
            ('PIC',6,0x2000,bytes(8200),'FALLBACK'),('PIC',6,0xE001,bytes(8192),'FALLBACK'),
            ('PIC',6,0x8400,bytes(8192),'RUN'),('PIC',8,0x2000,bytes(8192),'FALLBACK'),
            ('PIC',6,0,b'DGR\1\x50\x30\1\0'+bytes(8184),'FALLBACK'),
            ('DOG.SHP',6,0x1DF0,b'\x4c\0\x20'+bytes(8717),'IMAGE'),('DOG.SHP',6,0x1DF0,bytes(8721),'FALLBACK'),
            ('JIMMY',6,0x63D0,hi(b'Dear Jimmy,\r')*60,'DOCVIEW'),('JIMMY',6,0x0840,hi(b'Hi\r'),'DOCVIEW'),
            ('JIMMY',6,0x2000,hi(b'Hi\r'),'FALLBACK'),('JIMMY',6,0,hi(b'Hi')+b'\r','FALLBACK'),('T.S',6,0,hi(b' LDA #0\r'),'MERLIN'),
            ('ROCKET.LOGO',6,0x2000,b'TO ROCKET\rFD 10\rEND\r','TEXT'),('.LOGO',6,0x2000,b'TO X\r','FALLBACK'),
            ('NARROW',6,0,bytes((5,10))+b'gs\0'+bytes(60),'ARLEQUIN'),
            ('MAKE.TEXT',0xFC,0x0801,b'\x0a\x08\x0a\0\xba"A"\0\0\0','RUN'),('MAKE.TEXT',4,0,b'x\r','FALLBACK'),('PROG.TEXT',6,0,bytes(2048),'PASTEXT'),('PROG.TEXT',0,0,bytes(3072),'PASTEXT'),
            ('PROG.TEXT',6,0,bytes(1024),'FALLBACK'),('PROG.TEXT',6,0,bytes(2049),'FALLBACK'),('PROG.TEXT',4,0,bytes(2048),'FALLBACK'),('PROG',3,0,b'x','PASTEXT')):
            with self.subTest(name=name,typ=typ,aux=aux,size=len(data),exe=exe):
                self.check(data,expected,typ=typ,aux=aux,size=len(data),arg=O,exe=exe,name=name)

    def test_open_metadata_routes(self):self.open_metadata_cases()

    def test_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            exe=self.p/target;self.compile(exe,target,cpu);self.cases(exe);self.visicalc_cases(exe);self.originals(exe);self.printshop_cases(exe);self.movie_cases(exe);self.pcs_cases(exe);self.dpc_cases(exe);self.multiscr_cases(exe);self.mouse_bin_cases(exe);self.multiplan_bin_cases(exe);self.lisa_bin_cases(exe);self.sc_bin_cases(exe);self.arlequin_bin_cases(exe);self.macpaint_cases(exe);self.open_metadata_cases(exe);self.basint_cases(exe);self.lisa4_cases(exe)

if __name__=='__main__':unittest.main()
