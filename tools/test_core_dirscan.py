"""Core recursive operations must distinguish incomplete directories from EOF."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import SOURCE, section

HARNESS = r'''
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
static unsigned char copy_buf[512];
static int dir_fd=-1;
static FILE* img_f;
static unsigned char dir_img,dir_error,dir_index,dir_per_block,dir_entry_len;
struct DirEntry {char name[17]; unsigned char type,access;unsigned int key,blocks,aux,mdate;unsigned long size;};
static struct DirEntry dir_entry;
struct Mini {char name[16];unsigned char type;unsigned int aux;};
#define POOL_SIZE 213
static struct Mini pool[POOL_SIZE];
static unsigned char img_read_block(unsigned int b,unsigned char* buf) {return 0;}
''' + section('static unsigned char dir_open(const char* path)\n{', '/* ---------------------------------------------------------------------- */\n/* Display') + section('static unsigned char list_dir(const char* path,', '/* Appends "/name"') + r'''
int main(int argc,char**argv) {
    unsigned char n=0,ok=list_dir(argv[1],0,&n);
    printf("%u %u %u\n",ok,n,dir_error);return 0;
}
'''

class CoreDirscan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='core-dir-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99',str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def scan(self,length,linked,name=None):
        d=bytearray(length);d[4]=0xF1;d[35:37]=bytes([39,13]);d[2:4]=linked.to_bytes(2,'little')
        d[43:45]=b'\x11A';d[59]=6
        if name is not None:
            d[43]=0x10|len(name);d[44:44+len(name)]=name
        f=self.p/'dir';f.write_bytes(d)
        result=subprocess.check_output([self.exe,f],text=True)
        self.assertEqual(f.read_bytes(),d)
        return list(map(int,result.split()))
    def test_malformed_names_cannot_redirect_file_operations(self):
        for name in (b'',b'..',b'A/B',b'A:B',b'A\x00B',b'1BAD'):
            with self.subTest(name=name):self.assertEqual(self.scan(512,0,name),[0,0,1])

    def test_normal_end(self):self.assertEqual(self.scan(512,0),[1,1,0])
    def test_missing_next_block(self):self.assertEqual(self.scan(512,3),[0,1,1])
    def test_partial_next_block(self):self.assertEqual(self.scan(768,3),[0,1,1])
    def test_complete_next_block(self):self.assertEqual(self.scan(1024,3),[1,1,0])
if __name__=='__main__':unittest.main()
