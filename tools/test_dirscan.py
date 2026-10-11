"""Actual directory iterator: root GET_FILE_INFO describes the whole volume."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT

HARNESS=PREFIX+r'''
#define ferror mock_error
static FILE* errored;
static int mock_error(FILE* f){return f==errored;}
#define UTIL_INFO
#include "src/plugins/util.h"
#include "src/plugins/dirscan.h"
static const char* disk;
static unsigned int storage,allocated,reads;
static int fault;
static size_t read_dir(void* p,size_t s,size_t n,FILE* f){
    size_t got=fread(p,s,n,f);if(++reads==fault)errored=f;return got;
}
static int close_dir(FILE* f){errored=0;return fclose(f);}
static FILE* open_dir(const char* path,const char* mode) { return fopen(disk,mode); }
static unsigned char mock(unsigned char cmd,void* p) {
    struct Info* i=p;if(cmd!=0xC4)abort();i->storage=storage;i->blocks=allocated;return 0;
}
int main(int argc,char**argv) {
    unsigned char scratch[512],r;unsigned int blocks,count=0;unsigned long pos=0;
    fault=argc>4 ? atoi(argv[4]):0;
    disk=argv[1];storage=atoi(argv[2]);allocated=atoi(argv[3]);buf=scratch;
    a.strlen=strlen;a.strcpy=strcpy;a.strcmp=strcmp;a.memcpy=memcpy;
    a.mli=mock;a.fopen=open_dir;a.fread=read_dir;a.fclose=close_dir;a.fseek=fseek;
    dir_reset();r=dir_begin("/ROOT",&blocks);
    if(r)while((r=dir_next("/ROOT",blocks,&pos))==1)++count;
    else r=2;
    printf("%u %u %u\n",r,blocks,count);
}
'''
class DirectoryScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dirscan-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS);cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def scan(self,n,allocated=1200,storage=15,truncated=False,name=b'A',fault=0):
        d=bytearray(n*512)
        for i in range(n):
            d[i*512+2:i*512+4]=(i+3 if i<n-1 or truncated else 0).to_bytes(2,'little')
            off=i*512+(43 if not i else 4)
            d[off]=0x10|len(name);d[off+1:off+1+len(name)]=name
        d[4]=(15 if storage==15 else 14)<<4|1;d[5]=ord('V');d[35:37]=bytes([39,13])
        disk=self.p/'dir.bin';disk.write_bytes(d)
        out=subprocess.check_output([self.exe,str(disk),str(storage),str(allocated),str(fault)],text=True)
        self.assertEqual(disk.read_bytes(),d)
        return list(map(int,out.split()))
    def test_volume_allocation_is_not_root_length(self):self.assertEqual(self.scan(4),[0,4,4])
    def test_one_block_root(self):self.assertEqual(self.scan(1),[0,1,1])
    def test_longer_root(self):self.assertEqual(self.scan(5),[0,5,5])
    def test_missing_linked_block_is_error(self):self.assertEqual(self.scan(4,truncated=True)[0],2)
    def test_allocation_bounds_bad_root_chain(self):self.assertEqual(self.scan(4,allocated=2)[0],2)
    def test_subdirectory_keeps_its_actual_count(self):self.assertEqual(self.scan(4,allocated=4,storage=13),[0,4,4])
    def test_full_count_with_error_never_exposes_the_failed_block(self):
        for storage,at,count in ((15,1,0),(15,4,0),(15,5,0),(15,8,3),
                                 (13,1,0),(13,4,3)):
            with self.subTest(storage=storage,read=at):
                result=self.scan(4,allocated=4,storage=storage,fault=at)
                self.assertEqual(result[0],2)
                self.assertEqual(result[2],count)

    def test_invalid_names_are_errors_before_exposing_an_entry(self):
        for name in (b'../VICTIM',b'A/B',b'A\0B',b'.BAD',b'9BAD',b'BAD NAME',b'A\x80',b'A\\B',b'lower'):
            with self.subTest(name=name):self.assertEqual(self.scan(1,name=name),[2,1,0])
    def test_valid_names_and_lengths_still_scan(self):
        for name in (b'A',b'A.9',b'ABCDEFGHIJKLMNO',b'A23456789.12345'):
            with self.subTest(name=name):self.assertEqual(self.scan(1,name=name),[0,1,1])
if __name__=='__main__':unittest.main()
