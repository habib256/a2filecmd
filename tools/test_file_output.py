"""Execute resident reservation states and the output wrapper on both CPUs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <stdio.h>
#include <fcntl.h>
static unsigned char mode, entry, closes, opens, removes;
static int create_file(const char* p,int flags) {
    if(flags!=(O_WRONLY|O_CREAT|O_EXCL))return -1;
    if(mode==1 || entry)return -1;
    entry='E';return 7;
}
static int close_file(int fd) {++closes;return mode==3 || mode==5?-1:0;}
static FILE* reopen(const char* p,const char* m) {
    ++opens;return mode==4 || mode==6?NULL:(FILE*)0x1234;
}
static int discard(const char* p) {
    ++removes;if(mode==5 || mode==6)return -1;entry=0;return 0;
}
#define open create_file
#define close close_file
#define fopen reopen
#define remove discard
#include "src/file_output.h"
static void reset(void) {entry=mode==2?'P':0;closes=opens=removes=0;}
int main(void) {
    unsigned char status, i;
    FILE* f;
    for(i=0;i<3;++i)for(mode=0;mode<7;++mode) {
        reset();status=reserve_output("/V/OUT");
        if(mode==1 || mode==2) {
            if(status || closes || opens || removes || entry!=(mode==2?'P':0))return 1;
        } else if(status!=(mode==3 || mode==5?OUTPUT_CLOSE_FAILED:OUTPUT_RESERVED) ||
                  entry!='E' || closes!=1 || opens || removes)return 2;
        reset();f=new_output("/V/OUT");
        if((f!=NULL)!=(mode==0))return 3;
        if(mode==1 || mode==2) {
            if(closes || opens || removes || entry!=(mode==2?'P':0))return 4;
        } else {
            if(closes!=1 || opens!=(mode==3 || mode==5?0:1) || removes!=(mode?1:0))return 5;
            if(entry!=(mode==0 || mode==5 || mode==6?'E':0))return 6;
        }
    }
    return 0;
}
'''


class FileOutput(unittest.TestCase):
    def test_native_reservation_ownership(self):
        with tempfile.TemporaryDirectory(prefix='file-output-') as d:
            p = Path(d)
            source = p / 'test.c'
            source.write_text(C)
            for cpu in ('sim6502', 'sim65c02'):
                with self.subTest(cpu=cpu):
                    result = subprocess.run(
                        [shutil.which('cl65'), '-t', cpu, '-O', '-Oirs', '-Cl',
                         '-I', str(ROOT), '-o', str(p / 'test'), str(source)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    subprocess.run([shutil.which('sim65'), str(p / 'test')],
                                   check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
