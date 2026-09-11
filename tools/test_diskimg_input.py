"""DISKIMG rejects malformed or stale image sources before destructive use."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import section

HARNESS=r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#define SIDE_PO 1
#define SIDE_DSK 2
static char full[256];
static unsigned char data[512];
#define DI_BLOCK data
struct Side {unsigned char kind;FILE* f;unsigned long base;};
struct Entry {char name[17];unsigned long size;};
static struct {unsigned int total;} state;
#define DI (&state)
static int fault;
static int seek(FILE* f,long off,int whence) {return fault?-1:fseek(f,off,whence);}
#define fseek seek
'''+section('static unsigned char di_open_image(', 'static const char* di_error(')+r'''
int main(int argc,char**argv) {
    struct Entry e;struct Side s;unsigned char ok;
    strcpy(full,argv[1]);strcpy(e.name,argv[2]);e.size=strtoul(argv[3],0,10);fault=atoi(argv[4]);
    ok=di_open_image(&s,&e);if(s.f)fclose(s.f);
    printf("%u\n",ok);return 0;
}
'''

class DiskInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='di-input-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99',str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def check(self,data,name='IMAGE.2MG',cached=None,fault=0):
        f=self.p/'image';f.write_bytes(data)
        result=int(subprocess.check_output([self.exe,f,name,str(len(data) if cached is None else cached),str(fault)],text=True))
        self.assertEqual(f.read_bytes(),data);return result
    def image(self,base=64,size=512,fmt=1):
        h=bytearray(64);h[:4]=b'2IMG';h[12:16]=fmt.to_bytes(4,'little')
        h[24:28]=base.to_bytes(4,'little');h[28:32]=size.to_bytes(4,'little')
        return bytes(h)+bytes(512)
    def test_valid_sources(self):
        self.assertEqual(self.check(self.image()),1)
        self.assertEqual(self.check(bytes(512),'IMAGE.PO'),1)
        self.assertEqual(self.check(bytes(4096),'IMAGE.DSK'),1)
    def test_invalid_2mg_ranges_and_format(self):
        for data in (self.image(base=0),self.image(base=32),self.image(base=1000),
                     self.image(size=1024),self.image(size=0),self.image(fmt=256),self.image()[:-1]):
            with self.subTest(header=data[:32]):self.assertEqual(self.check(data),0)
    def test_partial_blocks_and_tracks(self):
        self.assertEqual(self.check(bytes(511),'IMAGE.PO'),0)
        self.assertEqual(self.check(bytes(512),'IMAGE.DSK'),0)
    def test_stale_size_and_failed_seek(self):
        self.assertEqual(self.check(self.image(),cached=1024),0)
        self.assertEqual(self.check(self.image(),fault=1),0)
if __name__=='__main__':unittest.main()
