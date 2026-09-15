"""Run the actual staged DISKIMG copy loop with injected device failures.

The single-drive copy runs against three stand-in floppies (the source, the
target and a stranger) and a script of what the user inserts at each prompt:
an out-of-step swap must never write onto the source or a stranger, nor
read the target as the source; the target keeps its mark until the last
pass.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'src/a2fc.c').read_text()


def section(start, end):
    a = SOURCE.index(start)
    return SOURCE[a:SOURCE.index(end, a)]


HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#define __fastcall__
#define DI_MAIN_BLOCKS 3
#define DI_AUX_BLOCKS 80
#define SIDE_DEVICE 0
#define NAME_LEN 17
#define KEY_ESC 27
struct Side { unsigned char kind, unit; };
struct DiskImg { struct Side src,dst; unsigned int total,checkblock; unsigned char checking,want,sr; const char* wrong; const unsigned char* rom; unsigned int first; char source[NAME_LEN]; } state;
#define DI (&state)
static unsigned char blockbuf[512], copy_buf[512], staged[83][512], disks[3][280][512], original[280][512];
#define DI_BLOCK blockbuf
static const char S_INSERT[] = "%sInsert %s for %s in %s. Key/ESC.", S_WRONG[] = "WRONG DISK. ", S_EMPTY[] = "";
static const char S_SOURCE[] = "SOURCE", S_TARGET[] = "TARGET copy", S_READING[] = "Reading", S_WRITING[] = "Writing";
static int progress_total,progress_done,writes,reads,asks,wrongs,mode,inserted=1,stranger_writes;
static const char* script = "";
static void progress_bar(const char* s,unsigned int d,unsigned int t) {}
static void question_begin(void) {}
static void revers(unsigned char r) {}
static const char* di_where(unsigned char u) { return "slot 6 drive 1"; }
static void cprintf(const char* f, ...) { va_list a; va_start(a, f); if (va_arg(a, const char*) == S_WRONG) ++wrongs; va_end(a); }
/* S, T, X: the source, the target or a stranger goes in; E: Escape */
static char cgetc(void) {
    char c = script[asks];
    if (c) ++asks;
    if (!c || c == 'E') return KEY_ESC;
    inserted = c == 'S' ? 0 : c == 'T' ? 1 : 2;
    return 13;
}
static unsigned char di_presize(struct Side* s,unsigned int n) { return 0; }
static void di_stage(unsigned char i,unsigned char put) {
    if (i >= 83) abort();
    if(put)memcpy(staged[i],blockbuf,512);else memcpy(blockbuf,staged[i],512);
}
static unsigned char di_xfer(struct Side* s,unsigned int b,unsigned char write) {
    int d;
    if (b >= 280) abort();
    if (s->kind != SIDE_DEVICE) { if (!write) abort(); ++writes; memcpy(disks[1][b],blockbuf,512); return 0; }
    d = state.src.unit == state.dst.unit ? inserted : s == &state.src ? 0 : 1;
    if(write) {
        ++writes; if(mode==3 && b==7)return 0x2B;
        if(mode==8 && d==1)return 0x2B;             /* the target is write protected */
        if(d==2)++stranger_writes;
        memcpy(disks[d][b],blockbuf,512);
    } else {
        if (s == &state.dst) ++reads;
        if(mode==2 && b==7 && s==&state.dst)return 0x27;
        if(mode==7 && b==2 && d==0)return 0x27;
        memcpy(blockbuf,disks[d][b],512);
        if(mode==1 && b==7 && s==&state.dst)blockbuf[511]^=1;
    }
    return 0;
}
''' + section('#define DI_MARK', '/* A .DSK image writes its sectors') \
    + section('static unsigned char di_copy(', '#ifndef DI_SLOTROM') + r'''
static unsigned char pattern(int d, unsigned b, unsigned i) {
    return d == 0 ? (b*7+i*13)&255 : d == 1 ? ((b*11+i*3+1)&255)^0x5A : (b+i*29+7)&255;
}
int main(int argc,char**argv) {
    unsigned int b,i,d; unsigned char result; int source_intact=1, copied=1;
    mode=atoi(argv[1]); if (argc > 3) script = argv[3];
    for(d=0;d<3;++d)for(b=0;b<280;++b)for(i=0;i<512;++i)disks[d][b][i]=pattern(d,b,i);
    if(mode==6)memcpy(disks[1],disks[0],sizeof disks[0]);    /* two identical disks */
    if(mode==9)memset(disks[0][2],0xA5,512);                 /* the source is a target left marked */
    memcpy(original,disks[0],sizeof original);
    DI->total=280; DI->dst.kind=mode==4 ? 1 : 0;
    DI->src.unit=0x60; DI->dst.unit=atoi(argv[2]) ? 0x60 : 0xE0;
    result=di_copy(atoi(argv[2]));
    if(memcmp(disks[0],original,sizeof original))source_intact=0;
    if(memcmp(disks[1],original,sizeof original))copied=0;
    printf("%u %u %u %u %u %u %u %d %d %d\n",result,writes,reads,DI->checking,DI->checkblock,asks,wrongs,source_intact,copied,stranger_writes);
    return 0;
}
'''


class Diskimg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='diskimg-readback-')
        p=Path(cls.tmp.name); (p/'test.c').write_text(HARNESS); cls.exe=p/'test'
        r=subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(cls.exe)],capture_output=True,text=True)
        if r.returncode: raise RuntimeError(r.stderr)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def run_copy(self,mode=0,swap=0,script=''):
        return list(map(int,subprocess.check_output([self.exe,str(mode),str(swap),script],text=True).split()))
    def test_every_written_block_is_read_back(self):
        self.assertEqual(self.run_copy(),[0,280,280,0,279,0,0,1,1,0])
    def test_single_drive_verifies_without_extra_swaps(self):
        # the mark, then four passes of 83 blocks from the end; blocks 0-30 last
        self.assertEqual(self.run_copy(swap=1,script='ST'*4),[0,281,280,0,30,8,0,1,1,0])
    def test_mismatch_stops_before_next_write(self):
        self.assertEqual(self.run_copy(1),[254,8,8,1,7,0,0,1,0,0])
    def test_read_error_identifies_first_block(self):
        self.assertEqual(self.run_copy(2),[39,8,8,1,7,0,0,1,0,0])
    def test_write_error_is_not_a_readback_error(self):
        self.assertEqual(self.run_copy(3),[43,8,7,0,6,0,0,1,0,0])
    def test_image_output_is_not_read_through_write_only_stream(self):
        self.assertEqual(self.run_copy(4),[0,280,0,0,0,0,0,1,1,0])
    def test_cancel_before_target_writes_only_the_mark(self):
        self.assertEqual(self.run_copy(5,1,'SE'),[255,1,0,0,0,2,0,1,0,0])
    def test_target_left_in_at_a_source_prompt_is_asked_again(self):
        # a pass starts with the target still in the drive: its blocks are
        # not staged, so nothing of it can later be written back
        for script, wrong in (('TSTSTSTST', 1), ('STTSTSTST', 1), ('STSTTTSTST', 2), ('STSTSTTST', 1)):
            with self.subTest(script=script):
                self.assertEqual(self.run_copy(0,1,script),[0,281,280,0,30,len(script),wrong,1,1,0])
    def test_source_or_stranger_at_a_target_prompt_is_asked_again(self):
        for script in ('SSTSTSTST', 'SXTSTSTST', 'STSXSTSTST', 'STSTSTSST', 'STSTSTSXST'):
            with self.subTest(script=script):
                self.assertEqual(self.run_copy(0,1,script),[0,281,280,0,30,len(script),len(script)-8,1,1,0])
    def test_identical_disks_are_told_apart_by_the_mark(self):
        self.assertEqual(self.run_copy(6,1,'SSTSTSTST'),[0,281,280,0,30,9,1,1,1,0])
    def test_marked_source_is_refused(self):
        self.assertEqual(self.run_copy(9,1,'SSE'),[255,1,0,0,0,3,2,1,0,0])
    def test_read_error_at_a_prompt_stops_before_copying(self):
        self.assertEqual(self.run_copy(7,1,'S'),[39,1,0,0,0,1,0,1,0,0])
    def test_protected_target_stops_at_the_mark(self):
        self.assertEqual(self.run_copy(8,1,'ST'),[43,1,0,0,0,0,0,1,0,0])
if __name__=='__main__': unittest.main()
