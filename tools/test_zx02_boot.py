"""Actual experimental launcher C: round trips, bounds and failed I/O."""
import binascii
import os
import random
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from zx02_image import pack

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static struct { unsigned char before[16], data[35552], after[16]; } memory;
static int fault, reads, bad, launched;
static const char* input;
static void set_boot_prefix(void) {}
static FILE* open_image(const char* p,const char* mode) {return fopen(input,mode);}
static size_t read_image(void* p,size_t s,size_t n,FILE* f) {
 ++reads;
 if(fault==1 && reads==1) {bad=1;return 0;}
 if(fault==2 && reads==2) {bad=1;return fread(p,s,n?n-1:0,f);}
 if((fault==6 && reads==3)||(fault==7 && reads==4)) {bad=1;return fread(p,s,n?n-1:0,f);}
 if(fault==8 && reads==3) {size_t got=fread(p,s,n,f);bad=1;return got;}
 return fread(p,s,n,f);
}
static int close_image(FILE* f){int r=fclose(f);return fault==3?-1:r;}
static int error_image(FILE* f){return bad || ferror(f);}
#define fopen open_image
#define fread read_image
#define fclose close_image
#define ferror error_image
#define ZX_AT(i) (memory.data+(i))
#ifdef A2FC_ZX02_ASM
unsigned char* zx_test_output = memory.data;
#endif
#define ZX_LAUNCH() (++launched)
#define main boot_main
#include "src/zxloader.c"
#undef main
#undef fread
#undef fclose
#undef fopen
int main(int argc,char**argv) {
 FILE* out;unsigned i,limit;int result;static unsigned char header[12];
 input=argv[1];fault=atoi(argv[2]);memset(&memory,0xA5,sizeof(memory));
 out=fopen(input,"rb");limit=fread(header,1,12,out)==12?(header[4]|((unsigned)header[5]<<8)):0;fclose(out);
 result=boot_main();
 for(i=0;i<16;++i)if(memory.before[i]!=0xA5 || memory.after[i]!=0xA5)return 9;
 if(limit>0xC00 && limit<=sizeof(memory.data))
  for(i=limit;i<sizeof(memory.data);++i)if(memory.data[i]!=0xA5)return 10;
 if(fault==5)for(i=0;i<sizeof(memory.data);++i)if(memory.data[i]!=0xA5)return 11;
 if(!result && launched==1){
   if(fault==4)return 0; /* cycle measurement without output-file copies */
   out=fopen(argv[3],"wb");if(!out)return 8;
   fwrite(memory.data,1,zx_pos,out);fclose(out);return 0;
 }
 return launched?7:1;
}
'''
CONIO = r'''
#define VIDEOMODE_80COL 0
static void videomode(int m) {}
static void clrscr(void) {}
static void cputs(const char* s) {}
static int cgetc(void) { return 0; }
'''


class ZXBoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        requested = os.environ.get('ZX02','zx02')
        cls.zx02 = shutil.which(requested) or requested
        if not Path(cls.zx02).exists():
            raise unittest.SkipTest('set ZX02 to dmsc/zx02 compressor')
        cls.tmp = tempfile.TemporaryDirectory(prefix='zxboot-test-')
        cls.p = Path(cls.tmp.name)
        (cls.p/'h.c').write_text(HARNESS)
        (cls.p/'conio.h').write_text(CONIO)
        cls.exe = cls.p/'host'
        subprocess.run(['cc','-std=c99','-fsanitize=address,undefined','-I',str(cls.p),'-I',str(ROOT),str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)
        cls.assembly = {}
        if shutil.which('cl65'):
            for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
                exe = cls.p/target
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-DA2FC_ZX02_ASM','--asm-define','ZX02_TEST_LINEAR','-I',str(cls.p),'-I',str(ROOT),'-I',str(ROOT/'src'),*(['-DA2FC_6502'] if cpu=='6502' else []),'-o',str(exe),str(cls.p/'h.c'),str(ROOT/'src/zx02_decode.s')],check=True,capture_output=True)
                cls.assembly[cpu] = exe
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def encode(self, raw, cpu=1):
        source, dest = self.p/'raw', self.p/'encoded'
        source.write_bytes(raw)
        dest.unlink(missing_ok=True)
        pack(source,dest,Path(self.zx02),cpu)
        return dest.read_bytes()
    def run_image(self,data,success=False,raw=None,fault=0,exe=None):
        if exe is None:
            self.run_image(data,success,raw,fault,[str(self.exe)])
            for cpu,program in self.assembly.items():
                image=bytearray(data)
                if cpu=='6502' and len(image)>10:image[10]^=1
                self.run_image(bytes(image),success,raw,fault,['sim65',str(program)])
            return
        src,out = self.p/'test.img',self.p/'decoded'
        src.write_bytes(data);out.unlink(missing_ok=True)
        r=subprocess.run((exe or [str(self.exe)])+[str(src),str(fault),str(out)],capture_output=True,timeout=120)
        self.assertEqual(r.returncode,0 if success else 1,r.stderr.decode(errors='replace'))
        self.assertEqual(src.read_bytes(),data)
        if success:self.assertEqual(out.read_bytes(),raw)
        else:self.assertFalse(out.exists())
    def test_round_trips_and_output_boundary(self):
        rng=random.Random(2)
        for raw in (b'A'*0xC01, bytes(range(256))*138+bytes(range(224)), rng.randbytes(35000), (ROOT/'build/A2FILE.CODE.BIN').read_bytes()):
            encoded=self.encode(raw);self.run_image(encoded,True,raw)
            if len(encoded)>4096:self.run_image(encoded,fault=7)
    def test_extent_crc_cpu_and_io_errors(self):
        raw=bytes(range(256))*32;d=self.encode(raw)
        for fault in (1,2,3,6,8):self.run_image(d,fault=fault)
        for offset in (0,4,6,8,10,11):
            bad=bytearray(d);bad[offset]^=0x40;self.run_image(bad)
        for cut in (0,1,11,12,len(d)//2,len(d)-1):self.run_image(d[:cut])
        for at in (12,511):
            bad=bytearray(d);bad[at]=1;self.run_image(bad)
        # Old unaligned v1 streams remain readable.
        self.run_image(d[:3]+b'1'+d[4:12]+d[512:],True,raw)
        self.run_image(d+b'\x00')
        for size in (0,0xC00,0x8AE1,65535):
            self.run_image(d[:4]+struct.pack('<H',size)+d[6:])
    def test_malformed_stream_never_escapes_output(self):
        rng=random.Random(17)
        for n in range(1,100):
            payload=rng.randbytes(n)
            self.run_image(struct.pack('<4sHHHBB',b'A2Z1',0xC01,n,0,1,0)+payload)
    def test_invalid_gamma_reference_and_run_bound(self):
        class Bits:
            def __init__(self):self.data=bytearray();self.mask=0
            def bit(self,b):
                if not self.mask:self.at=len(self.data);self.data.append(0);self.mask=128
                if b:self.data[self.at]|=self.mask
                self.mask>>=1
            def byte(self,b):self.data.append(b)
            def elias(self,n):
                for b in bin(n)[3:]:self.bit(1);self.bit(int(b))
                self.bit(0)
        def envelope(b):return struct.pack('<4sHHHBB',b'A2Z1',0xC01,len(b.data),0,1,0)+b.data
        b=Bits();b.elias(257)
        for _ in range(257):b.byte(90)
        self.run_image(envelope(b),fault=5)  # reject before the first write
        for msb in (1,255,256):
            b=Bits();b.elias(1);b.byte(65);b.bit(1);b.elias(msb)
            if msb!=256:b.byte(2) # distance 2 (or much larger), only 1 byte exists
            self.run_image(envelope(b))
        b=Bits()
        for _ in range(6):
            b.elias(256)
            for _ in range(256):b.byte(90)
            b.bit(0);b.elias(256);b.bit(0)
        b.elias(2);b.byte(90);b.byte(90) # only one output byte remains
        self.run_image(envelope(b))
    def test_exclusive_output(self):
        src,dest=self.p/'raw',self.p/'encoded'
        src.write_bytes(b'A'*4000);dest.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):pack(src,dest,Path(self.zx02),1)
        self.assertEqual(dest.read_bytes(),b'preserve')
    def test_both_real_cpus(self):
        if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            exe=self.assembly[cpu]
            raw=(ROOT/('build-6502' if cpu=='6502' else 'build')/'A2FILE.CODE.BIN').read_bytes()
            d=self.encode(raw,int(cpu!='6502'))
            self.run_image(d,True,raw,exe=['sim65',str(exe)])
            src,out=self.p/'test.img',self.p/'decoded'
            measured=subprocess.run(['sim65','-c',str(exe),str(src),'4',str(out)],check=True,capture_output=True,text=True)
            print(cpu,'ASM',measured.stdout.strip(),measured.stderr.strip())
            # Complete launcher/harness budget for the current release cores.
            # Keep Disk II's accepted few-second overhead from regressing.
            cycles=re.search(r'(\d+) cycles',measured.stdout+measured.stderr)
            self.assertIsNotNone(cycles)
            self.assertLess(int(cycles[1]),8_000_000)
            reference=self.p/(target+'-reference')
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-I',str(self.p),'-I',str(ROOT),*(['-DA2FC_6502'] if cpu=='6502' else []),'-o',str(reference),str(self.p/'h.c')],check=True,capture_output=True)
            measured=subprocess.run(['sim65','-c',str(reference),str(src),'4',str(out)],check=True,capture_output=True,text=True)
            print(cpu,'C',measured.stdout.strip(),measured.stderr.strip())
            self.run_image(d[:-1],exe=['sim65',str(exe)])
            self.run_image(d,fault=3,exe=['sim65',str(exe)])


if __name__=='__main__':unittest.main()
