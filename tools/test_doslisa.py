"""Existing LISA v2 decoder on immutable DOS alternate-B sources."""
import gzip
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from test_retrotext import lisa
from mini33_fixture import make_disk, offset

H = BASE.replace('#include "src/plugins/dosint.c"', '#include "src/plugins/lisav2.c"')

def disk(b):
    return make_disk([('TEXT', 0x40, b)])

def largest():
    return lisa(*([b'*'+b'X'*253+b'\r']*255+[b'*'+b'Y'*248+b'\r']))

class DOSLisa(unittest.TestCase):
    run_disk = D.Streams.run_disk
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='doslisa-', dir='/tmp')
        cls.p = Path(cls.tmp.name);cls.h = cls.p/'h.c';cls.h.write_text(H);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(D.ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def sample(self):return lisa(b'*comment\r',b'LABEL   \xcd\x02#$20\xbbnote\r',b' \xa0\0\r')
    def test_exact_listing_all_backends_and_stale_sizes(self):
        expected=b'\n*comment\nLABEL    LDA #$20            ;note\n         NOP'
        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,_,_=self.run_disk(disk(self.sample()),typ=0,image=image,size=size)
                self.assertTrue(out.startswith(expected),out)
    def test_every_read_open_seek_close_error_and_trailing_sectors(self):
        raw=disk(self.sample()+bytes(range(256))*3)
        for image in (0,1,2):
            _,counts,_=self.run_disk(raw,typ=0,image=image)
            for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                out,_,_=self.run_disk(raw,typ=0,image=image,fault=fault,good=False)
                if fault<=counts[1]//2 or fault in (1001,1002,1003,1004):self.assertEqual(out,b'')
    def test_truncation_malformed_records_catalog_aliases_and_raw_types(self):
        b=self.sample()
        for n in range(len(b)):
            self.run_disk(disk(b[:n]),typ=0,good=False)
        for at,v in ((2,0),(4,255),(-1,0),(-2,0),(-3,0)):
            bad=bytearray(b);bad[at]=v;self.run_disk(disk(bad),typ=0,good=False)
        for line in (b'\xcd\r',b'\xcd\0',b'LABEL   \x01\r',b' \xcd\x21\r'):
            self.run_disk(disk(lisa(line)),typ=0,good=False)
        raw=disk(b)
        bad=bytearray(raw);bad[offset(17,15)+14]^=1
        self.run_disk(bad,typ=0,key=783,good=False)
        raw=disk(b+bytes(512));bad=bytearray(raw);p=offset(3,15);bad[p+14:p+16]=bad[p+12:p+14]
        self.run_disk(bad,typ=0,good=False)
        # Other typeless DOS kinds cannot masquerade as alternate-B.
        for kind in (8,16,32):self.run_disk(make_disk([('TEXT',kind,b)]),typ=0,good=False)
        self.run_disk(disk(b),typ=6,good=False)
    def test_paging_cancellation_and_largest_declared_body(self):
        out,counts,_=self.run_disk(disk(lisa(*([b'*LINE\r']*80))),typ=0,image=1,keys='E')
        self.assertEqual(out.count(b'*LINE'),21);self.assertEqual(counts[2:4],[2,2])
        b=largest()
        self.assertEqual(int.from_bytes(b[2:4],'little'),65533)
        out,_,_=self.run_disk(disk(b),typ=0,keys='N'*1000)
        self.assertIn(b'YYY',out)
        self.run_disk(disk(b+bytes(256)),typ=0,good=False)
    def test_original_dos_sources_when_available(self):
        from legacy_corpus import dos_files
        p=Path.home()/'.cache/a2fc/cp2/fileconv_dos-files.do.gz'
        if not p.exists():self.skipTest('local LISA v2 corpus unavailable')
        count=0
        for name,typ,aux,b in dos_files(gzip.decompress(p.read_bytes())):
            if typ!=0xf4:continue
            with self.subTest(name=name):
                out,_,_=self.run_disk(disk(b),typ=0,image=1,keys='N'*1000)
                self.assertTrue(out);count+=1
        self.assertGreater(count,0)
    def test_cc65_both_cpus_and_late_read_faults(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(D.ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for image in (0,1,2):
                raw=disk(self.sample()+bytes(600))
                expected,counts,_=self.run_disk(raw,typ=0,image=image)
                actual,_,_=self.run_disk(raw,typ=0,image=image,exe=exe);self.assertEqual(actual,expected)
                for fault in (1,counts[1],*([1002,1003,1004] if image else [])):
                    self.run_disk(raw,typ=0,image=image,exe=exe,fault=fault,good=False)
            out,_,_=self.run_disk(disk(largest()),typ=0,image=1,exe=exe,keys='N'*1000)
            self.assertIn(b'YYY',out)

    def test_actual_idv1_stage_on_host_and_both_cpus(self):
        from test_six_plugins import PREFIX
        harness=PREFIX+r"""
unsigned char host_id_sample[512];
static const char* known(const char*,const char*);
#include "src/plugins/idv1.c"
void __fastcall__ plugin_entry(const struct A2fcApi* a){(void)a;}
static const char* known(const char* label,const char* view){reader=view;return label;}
int main(int argc,char** argv){
 static struct A2fcApi api;static struct Panel panels[2];static struct Entry entry;
 static unsigned char active,buffer[512];static char context[81],input[64],note[80];
 FILE* source;unsigned int length;unsigned char result;
 source=fopen(argv[1],"rb");if(!source)return 2;
 length=fread(host_id_sample,1,512,source);if(ferror(source)||fclose(source))return 3;
 strcpy(entry.name,"SOURCE");entry.type=atoi(argv[2]);entry.size=length;entry.mdate=783;
 panels[0].fs=atoi(argv[3])?FS_DOS33:FS_PRODOS;
 api.panels=panels;api.active=&active;api.selected=&entry;api.other_full=context;
 api.input=input;api.note=note;api.copy_buf=buffer;api.strcpy=strcpy;api.sprintf=sprintf;
 api.arg=atoi(argv[4]);strcpy(input,"UNCHANGED");id_context(&api,length,length,0,entry.type);
 if(atoi(argv[5]))context[48]^=1;
 result=md_entrypoint(&api);printf("%u %s %s\n",result,input,note);return 0;
}
"""
        src=self.p/'route.c';src.write_text(harness);host=self.p/'route'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(D.ROOT),str(src),'-o',str(host)],check=True,capture_output=True)
        commands=[[str(host)]]
        if shutil.which('cl65') and shutil.which('sim65'):
            root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
            for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
                cfg=self.p/(target+'-route.cfg');cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
                exe=self.p/('route-'+target)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(D.ROOT),*(['-DA2FC_6502'] if cpu=='6502' else []),'-o',str(exe),str(src)],check=True,capture_output=True)
                commands.append(['sim65',str(exe)])
        cases=[(self.sample(),0,1,0,'0 LISAV2 '),(self.sample(),0xf4,0,0,'1 UNCHANGED '),
               (b'\0\x19\x02\0',0,1,0,'1 UNCHANGED '),(self.sample(),0,1,1,'0 UNCHANGED Invalid identification'),
               (bytes(c|128 for c in b'AFILER 1.0')+bytes(20),6,1,0,'0 DOSVIEW ')]
        for cmd in commands:
            for b,typ,dos,corrupt,expected in cases:
                for arg in (13,ord('I'),ord('O')):
                    data=self.p/'sample';data.write_bytes(b)
                    r=subprocess.run(cmd+[str(data),str(typ),str(dos),str(arg),str(corrupt)],check=True,capture_output=True,text=True)
                    self.assertTrue(r.stdout.startswith(expected),r.stdout);self.assertEqual(data.read_bytes(),b)

        # Exercise IDFORMATS itself: its suffix lengths now use bytes.
        harness=harness.replace('#include "src/plugins/idv1.c"','#include "src/plugins/idformats.c"').replace('static const char* known(const char*,const char*);','').replace('static const char* known(const char* label,const char* view){reader=view;return label;}','').replace('strcpy(entry.name,"SOURCE");','strcpy(entry.name,argv[6]);')
        src=self.p/'suffix.c';src.write_text(harness);commands=[]
        for cpu,target in (('host',None),('6502','sim6502'),('65c02','sim65c02')):
            exe=self.p/('suffix-'+cpu)
            if target is None:
                subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(D.ROOT),str(src),'-o',str(exe)],check=True,capture_output=True)
                commands.append([str(exe)])
            elif shutil.which('cl65') and shutil.which('sim65'):
                cfg=self.p/(target+'-route.cfg')
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(D.ROOT),'-o',str(exe),str(src)],check=True,capture_output=True)
                commands.append(['sim65',str(exe)])
        b=bytes(c|128 for c in b'*OK\r');data=self.p/'suffix-source';data.write_bytes(b)
        for cmd in commands:
            for name,reader in [('ABCDEFGHIJKLMN.S','MERLIN'),('ABCDEFGHIJKL.ASM','MERLIN'),('A.S','MERLIN'),('A.ASM','MERLIN'),('.ASM',None),('S',None),('ABCDEFGHIJKLMNS',None),('A.SX',None)]:
                r=subprocess.run(cmd+[str(data),'4','1',str(ord('I')),'0',name],check=True,capture_output=True,text=True)
                self.assertTrue(r.stdout.startswith('0 MERLIN ' if reader else '1 UNCHANGED '),r.stdout)
                self.assertEqual(data.read_bytes(),b)

if __name__=='__main__':unittest.main()
