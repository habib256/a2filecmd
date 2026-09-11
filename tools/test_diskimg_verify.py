"""Run the actual staged DISKIMG copy loop with injected device failures."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'src/a2fc.c').read_text()
COPY = SOURCE[SOURCE.index('static unsigned char di_copy('):SOURCE.index('/* The block devices ProDOS knows')]
HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DI_MAIN_BLOCKS 3
#define DI_AUX_BLOCKS 80
#define SIDE_DEVICE 0
struct Side { unsigned char kind; };
struct DiskImg { struct Side src,dst; unsigned int total,checkblock; unsigned char checking; } state;
#define DI (&state)
static unsigned char blockbuf[512], copy_buf[512], staged[83][512], disk[280][512];
#define DI_BLOCK blockbuf
#define S_SOURCE "SOURCE"
#define S_TARGET "TARGET"
#define S_READING "Reading"
#define S_WRITING "Writing"
static int progress_total,progress_done,writes,reads,swaps,mode;
static void progress_bar(const char* s,unsigned int d,unsigned int t) {}
static unsigned char di_ask(const char* s) { ++swaps; return mode!=5 || swaps!=2; }
static unsigned char di_presize(struct Side* s,unsigned int n) { return 0; }
static void di_stage(unsigned char i,unsigned char put) {
    if(put)memcpy(staged[i],blockbuf,512);else memcpy(blockbuf,staged[i],512);
}
static unsigned char di_xfer(struct Side* s,unsigned int b,unsigned char write) {
    unsigned int i;
    if(s==&DI->src) { for(i=0;i<512;++i)blockbuf[i]=(b*7+i*13)&255; return 0; }
    if(write) {
        ++writes; if(mode==3 && b==7)return 0x2B;
        memcpy(disk[b],blockbuf,512);
    } else {
        ++reads; if(mode==2 && b==7)return 0x27;
        memcpy(blockbuf,disk[b],512);
        if(mode==1 && b==7)blockbuf[511]^=1;
    }
    return 0;
}
'''+COPY+r'''
int main(int argc,char**argv) {
    unsigned int b,i; unsigned char result;
    mode=atoi(argv[1]); DI->total=280; DI->dst.kind=mode==4 ? 1 : 0;
    result=di_copy(atoi(argv[2]));
    if(!result)for(b=0;b<280;++b)for(i=0;i<512;++i)
        if(disk[b][i]!=((b*7+i*13)&255))return 2;
    printf("%u %u %u %u %u %u\n",result,writes,reads,DI->checking,DI->checkblock,swaps);
}
'''

class Diskimg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='diskimg-readback-')
        p=Path(cls.tmp.name); (p/'test.c').write_text(HARNESS); cls.exe=p/'test'
        subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def run_copy(self,mode=0,swap=0):
        return list(map(int,subprocess.check_output([self.exe,str(mode),str(swap)],text=True).split()))
    def test_every_written_block_is_read_back(self):
        self.assertEqual(self.run_copy(),[0,280,280,0,279,0])
    def test_single_drive_verifies_without_extra_swaps(self):
        self.assertEqual(self.run_copy(swap=1),[0,280,280,0,279,8])
    def test_mismatch_stops_before_next_write(self):
        self.assertEqual(self.run_copy(1),[254,8,8,1,7,0])
    def test_read_error_identifies_first_block(self):
        self.assertEqual(self.run_copy(2),[39,8,8,1,7,0])
    def test_write_error_is_not_a_readback_error(self):
        self.assertEqual(self.run_copy(3),[43,8,7,0,6,0])
    def test_image_output_is_not_read_through_write_only_stream(self):
        self.assertEqual(self.run_copy(4),[0,280,0,0,0,0])
    def test_cancel_before_target_does_not_write(self):
        self.assertEqual(self.run_copy(5,1),[255,0,0,0,0,2])
if __name__=='__main__': unittest.main()
