"""Execute the direct Integer BASIC C pager with immutable DOS inputs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from mini33_fixture import make_disk
from test_intbasic import listing
ROOT=D.ROOT
HARNESS=D.HARNESS.replace('#include "src/plugins/dosview.c"','#include "src/plugins/dosint.c"')
HARNESS=HARNESS.replace('static void put(char c)','static void host_put(char c)').replace('api.cputc=put;', 'api.cputc=host_put;')
HARNESS=HARNESS.replace('api.panels=panels;', 'api.cgetc=key;api.memcpy=memcpy;api.memset=memset;api.strlen=strlen;api.sprintf=sprintf;api.bar_begin=clear;api.keys_bar=bar;api.panels=panels;')
HARNESS=HARNESS.replace('int main(int argc,char** argv){', 'static void bar(unsigned char x,const char* s){(void)x;(void)s;}\nint main(int argc,char** argv){')
a=HARNESS.index(' if(!strncmp(argv[9]');b=HARNESS.index(' fprintf(stderr',a)
HARNESS=HARNESS[:a]+' plugin_entry(&api);ok=!note[0];\n'+HARNESS[b:]


def program(lines=8):
    out=bytearray()
    for n in range(1,lines+1):
        body=bytes((0x61,0x28))+('LINE %d 123'%n).encode()+bytes((0x29,1))
        out+=bytes((len(body)+3,n*10&255,n*10>>8))+body
    return bytes(out)


def largest_program():
    data=b''.join(bytes((8,n&255,n>>8,0x61,0xb0,n&255,n>>8,1)) for n in range(8191))
    data+=bytes((7,0xff,0x1f,0x61,0xc1,0xb1,1))
    return data


class DOSINT(unittest.TestCase):
    run_disk=D.Streams.run_disk

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dosint-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'test.c';cls.h.write_text(HARNESS);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def disk(self,data):return make_disk([('TEXT',1,len(data).to_bytes(2,'little')+data)])

    def test_exact_listing_all_sources_and_stale_sizes(self):
        data=program();expected='\n'.join(listing(data))+'\n'
        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,_,_=self.run_disk(self.disk(data),typ=0xfa,image=image,size=size)
                self.assertTrue(out.decode().startswith(expected),out)

    def test_every_read_open_seek_close_failure(self):
        disk=self.disk(program(30))
        for image in (0,1,2):
            _,counts,_=self.run_disk(disk,typ=0xfa,image=image,keys='NN')
            faults=list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else [])
            for fault in faults:
                self.run_disk(disk,typ=0xfa,image=image,keys='NN',fault=fault,good=False)

    def test_malformed_records_truncation_and_wrong_types(self):
        data=program(1)
        for n in range(1,len(data)):
            self.run_disk(self.disk(data[:n]),typ=0xfa,good=False)
        for malformed in (bytes((3,10,0)),bytes((5,10,0,1,1)),bytes((5,10,0,0xb1,1)),
                          bytes((5,10,0,0x28,1)),bytes((5,10,0,0x29,1)),bytes((5,10,0,0x61,0))):
            self.run_disk(self.disk(malformed),typ=0xfa,good=False)
        self.run_disk(self.disk(data),typ=6,good=False)
        self.run_disk(self.disk(data),name='',key=0,typ=0xfa,good=False)

    def test_largest_integer_payload_and_allocation_bound(self):
        data=largest_program()
        self.assertEqual(len(data),65535)
        out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='N'*380)
        self.assertIn('8191 PRINT A1',out.decode())
        allocated=make_disk([('TEXT',1,b'\xff\xff'+data+bytes(256))])
        self.run_disk(allocated,typ=0xfa,good=False)
        too_long=bytes((255,10,0))+bytes((0x7a,))*251+bytes((1,))
        self.run_disk(self.disk(too_long),typ=0xfa,good=False)

    def test_paging_previous_restart(self):
        data=program(70)
        out,_,_=self.run_disk(self.disk(data),typ=0xfa,keys='NNBR')
        text=out.decode();self.assertIn('230 PRINT',text);self.assertIn('450 PRINT',text)
        self.assertGreaterEqual(text.count('10 PRINT'),2)

    def test_native_compiler_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        targets=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(targets/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1)
            config=self.p/(cpu+'.cfg');config.write_text(cfg);exe=self.p/cpu
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for image in (0,1,2):
                out,_,_=self.run_disk(self.disk(program()),typ=0xfa,image=image,exe=exe)
                self.assertTrue(out.decode().startswith('\n'.join(listing(program()))+'\n'))
                self.run_disk(self.disk(program()),typ=0xfa,image=image,fault=1,good=False,exe=exe)
            out,_,_=self.run_disk(self.disk(largest_program()),typ=0xfa,keys='N'*380,exe=exe)
            self.assertIn('8191 PRINT A1',out.decode())


if __name__=='__main__':unittest.main()
