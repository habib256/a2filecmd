"""Actual direct DOS Applesoft decoder/pager, immutable sources and faults."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as INTEGER_HARNESS
from mini33_fixture import make_disk
ROOT=D.ROOT
HARNESS=INTEGER_HARNESS.replace('src/plugins/dosint.c','src/plugins/dosbas.c')


def encode(records):
    out=bytearray()
    for number,body in records:
        link=0x0801+len(out)+5+len(body)
        out+=link.to_bytes(2,'little')+number.to_bytes(2,'little')+body+b'\0'
    return bytes(out)+b'\0\0'


def program(lines=8):
    return encode([(n*10,b'\xba"LINE '+str(n).encode()+b' 123"') for n in range(1,lines+1)])


class DOSBAS(unittest.TestCase):
    run_disk=D.Streams.run_disk

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dosbas-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'test.c';cls.h.write_text(HARNESS);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def disk(self,data):return make_disk([('TEXT',2,len(data).to_bytes(2,'little')+data)])

    def test_exact_listing_all_sources_stale_sizes_and_literal_contexts(self):
        data=encode([(10,b'\xba"A\x80Z"'),(20,b'\x83\x80,"A:B":\xba"OK"'),(30,b'\xb2\xba"COMMENT'),(40,b'\xba"UNTERMINATED')])

        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,_,_=self.run_disk(self.disk(data),typ=0xfc,image=image,size=size)
                text=out.decode();self.assertIn('10 PRINT "A.Z"',text)
                self.assertIn('20 DATA .,"A:B": PRINT "OK"',text)
                self.assertIn('30 REM :"COMMENT',text)
                self.assertIn('40 PRINT "UNTERMINATED',text)

    def test_all_keywords(self):
        # All 107 tokens must expand, including the final token $EA.
        data=encode([(i+1,bytes((i,))) for i in range(0x80,0xeb) if i not in (0x83,0xb2)])
        out,_,_=self.run_disk(self.disk(data),typ=0xfc,keys='N'*6)
        self.assertIn('END',out.decode());self.assertIn('MID$',out.decode())

    def test_every_read_open_seek_close_failure(self):
        disk=self.disk(program(30))
        for image in (0,1,2):
            _,counts,_=self.run_disk(disk,typ=0xfc,image=image,keys='NN')
            faults=list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else [])
            for fault in faults:self.run_disk(disk,typ=0xfc,image=image,keys='NN',fault=fault,good=False)

    def test_truncation_links_unknown_tokens_extra_bytes_and_wrong_types(self):
        data=program(1)
        for n in range(len(data)):self.run_disk(self.disk(data[:n]),typ=0xfc,good=False)
        for link in (1,0x0801,0x0802,0xffff):
            self.run_disk(self.disk(link.to_bytes(2,'little')+data[2:]),typ=0xfc,good=False)
        self.run_disk(self.disk(data+b'X'),typ=0xfc,good=False)
        self.run_disk(self.disk(encode([(10,b'\xeb')])),typ=0xfc,good=False)
        self.run_disk(self.disk(data),typ=0xfa,good=False)
        self.run_disk(self.disk(data),name='',key=0,typ=0xfc,good=False)
        self.run_disk(self.disk(b'\0\0'),typ=0xfc)

    def test_paging_previous_restart_and_overlong_line(self):
        out,_,_=self.run_disk(self.disk(program(70)),typ=0xfc,keys='NNBR')
        text=out.decode();self.assertIn('230 PRINT',text);self.assertIn('450 PRINT',text)
        self.assertGreaterEqual(text.count('10 PRINT'),2)
        self.run_disk(self.disk(encode([(10,b'\xb2'+b'X'*1800)])),typ=0xfc,good=False)

    def test_address_limit_and_ring_wrap(self):
        data=encode([(n,b'X') for n in range(10581)])
        self.assertEqual(len(data),63488)
        out,_,_=self.run_disk(self.disk(data),typ=0xfc,keys='N'*490)
        self.assertIn('10580 X',out.decode())
        overflow=data[:-2]+bytes((1,8,0xff,0x7f,ord('X'),0,0,0))
        self.run_disk(self.disk(overflow),typ=0xfc,keys='N'*490,good=False)

    def test_native_compiler_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        targets=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(targets/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1)
            config=self.p/(cpu+'.cfg');config.write_text(cfg);exe=self.p/cpu
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for image in (0,1,2):
                out,_,_=self.run_disk(self.disk(program()),typ=0xfc,image=image,exe=exe)
                self.assertTrue(out.decode().startswith('10 PRINT "LINE 1 123"\n'))
                self.run_disk(self.disk(program()),typ=0xfc,image=image,fault=1,good=False,exe=exe)
                self.run_disk(self.disk(program()[:-1]),typ=0xfc,image=image,good=False,exe=exe)
            literal=encode([(10,b'\xba"A\x80Z"'),(20,b'\x83\x80:')])
            out,_,_=self.run_disk(self.disk(literal),typ=0xfc,exe=exe)
            self.assertIn('10 PRINT "A.Z"',out.decode())
            self.assertIn('20 DATA .:',out.decode())
            data=encode([(n,b'X') for n in range(10581)])
            out,_,_=self.run_disk(self.disk(data),typ=0xfc,keys='N'*490,exe=exe)
            self.assertIn('10580 X',out.decode())
            overflow=data[:-2]+bytes((1,8,0xff,0x7f,ord('X'),0,0,0))
            self.run_disk(self.disk(overflow),typ=0xfc,keys='N'*490,good=False,exe=exe)


if __name__=='__main__':unittest.main()
