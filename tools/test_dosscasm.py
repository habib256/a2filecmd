"""Production S-C listing directly from immutable DOS sources, with faults."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from test_retrotext import sc_line
from mini33_fixture import make_disk
ROOT=D.ROOT
HARNESS=BASE.replace('src/plugins/dosint.c','src/plugins/scasm.c')
HARNESS=HARNESS.replace('return fault==1001?NULL:fopen(p,m);','return fault==1001 || (fault==1011 && opens==2)?NULL:fopen(p,m);')
HARNESS=HARNESS.replace('fclose(f)||fault==1002?', 'fclose(f)||fault==1002 || (fault==1012 && closes==2)?')


def program(lines=8):
    return b''.join(sc_line(n*10,b'\x89LDA\x83#'+str(n).encode()) for n in range(1,lines+1))


class DOSSCASM(unittest.TestCase):
    run_disk=D.Streams.run_disk

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dossc-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'test.c';cls.h.write_text(HARNESS);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def disk(self,data):return make_disk([('TEXT',1,len(data).to_bytes(2,'little')+data)])

    def test_exact_listing_spaces_rle_all_backends_and_stale_sizes(self):
        data=sc_line(100,b'\x89LDA\x83#0')+sc_line(65535,b'\xc0\x05*')
        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,counts,_=self.run_disk(self.disk(data),typ=0xfa,image=image,size=size)
                self.assertIn(b'0100          LDA   #0',out);self.assertIn(b'65535 *****',out)
                if image:self.assertEqual(counts[2:4],[2,2])

    def test_each_read_both_passes_and_open_seek_close_faults(self):
        disk=self.disk(program(70))
        for image in (0,1,2):
            _,counts,_=self.run_disk(disk,typ=0xfa,image=image,keys='N'*5)
            faults=list(range(1,counts[1]+1))+([1001,1002,1003,1004,1011,1012] if image else [])
            for fault in faults:self.run_disk(disk,typ=0xfa,image=image,keys='N'*5,fault=fault,good=False)

    def test_all_malformed_records_refused_before_display(self):
        data=sc_line(100,b'\x89LDA\x83#0')
        cases=[data[:n] for n in range(len(data))]
        cases += [sc_line(10,body) for body in (b'\0X',b'\xc0',b'\xc0\x04',b'\xc1',b'\xc0\xff\0')]
        cases += [bytes((3,10,0)),data[:-1]+b'X']
        for bad in cases:
            out,_,_=self.run_disk(self.disk(bad),typ=0xfa,good=False)
            self.assertFalse(out,out)
        self.run_disk(self.disk(data),typ=0xfc,good=False)
        self.run_disk(self.disk(data),name='',key=0,typ=0xfa,good=False)

    def test_paging_and_escape(self):
        data=program(70)
        out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='N'*5)
        self.assertIn(b'0700          LDA   #70',out)
        out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='E')
        self.assertIn(b'0010          LDA   #1',out);self.assertNotIn(b'0700',out)

    def test_full_integer_eof_and_excess_allocation(self):
        data=sc_line(65535,b'A')*13107
        self.assertEqual(len(data),65535)
        out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='N'*700)
        self.assertEqual(out.count(b'65535 A'),13107)
        oversized=make_disk([('TEXT',1,b'\xff\xff'+data+bytes(256))])
        self.run_disk(oversized,typ=0xfa,good=False)

    def test_original_dos_sc_sources_when_available(self):
        from legacy_corpus import dos_files
        disk=Path.home()/'.cache/a2fc/asimov_corpus/raw/images/programming/assembler/s-c/S-C Macro Assembler IIe (v1.1).dsk'
        if not disk.exists():self.skipTest('local S-C DOS corpus unavailable')
        raw=disk.read_bytes();found=0
        for name,typ,aux,data in dos_files(raw):
            if typ!=0xfa or not name.isalnum():continue
            self.run_disk(raw,name=name,typ=0xfa,keys='N'*700)
            found+=1
        self.assertGreater(found,0)

    def test_native_compiler_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        targets=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(targets/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1)
            config=self.p/(cpu+'.cfg');config.write_text(cfg);exe=self.p/cpu
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for image in (0,1,2):
                out,_,_=self.run_disk(self.disk(program()),typ=0xfa,image=image,exe=exe)
                self.assertIn(b'0010          LDA   #1',out)
                self.run_disk(self.disk(program()),typ=0xfa,image=image,fault=1,good=False,exe=exe)
                self.run_disk(self.disk(program()[:-1]),typ=0xfa,image=image,good=False,exe=exe)
            data=sc_line(65535,b'A')*13107
            out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='N'*700,exe=exe)
            self.assertEqual(out.count(b'65535 A'),13107)
            for fault in (1011,1012):self.run_disk(self.disk(program()),typ=0xfa,image=1,fault=fault,good=False,exe=exe)


if __name__=='__main__':unittest.main()
