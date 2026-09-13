"""Execute the shared CREATE request on both CPUs, with dirty overlay state."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <string.h>
#include <stddef.h>
#pragma static-locals(on)
static unsigned char pas[128], status, calls, bad;
static unsigned char expected_type, expected_storage;
static unsigned int expected_aux;
static unsigned char mli(unsigned char cmd, void* p);
static void prepare(const char* p) { pas[0]=strlen(p); strcpy((char*)pas+1,p); }
#define RF(name) name
#define FC_PATH pas
#define FC_PREPARE(path) prepare(path)
#include "src/plugins/file_create.h"
static unsigned char mli(unsigned char cmd, void* p) {
    struct Create* c=p;
    ++calls;
    if(cmd!=0xC0 || c->n!=7 || c->path!=pas || c->access!=0xC3 ||
       c->type!=expected_type || c->aux!=expected_aux ||
       c->storage!=expected_storage || c->date || c->time)bad=1;
    return status;
}
int main(void) {
    unsigned int r;
    if(sizeof(struct Create)!=12 || offsetof(struct Create,aux)!=5 ||
       offsetof(struct Create,time)!=10)return 1;
    for(r=0;r<256;++r) {
        memset(&create,0xA5,sizeof create); memset(pas,0xA5,sizeof pas);
        status=r; calls=bad=0;
        expected_type=6; expected_aux=0x2000; expected_storage=1;
        if(newfile("/VOL/FILE",6,0x2000,1)!=status || calls!=1 || bad ||
           pas[0]!=9 || strcmp((char*)pas+1,"/VOL/FILE"))return 2;
        /* A directory request follows the file, including after failure. */
        status=0; calls=0;
        expected_type=15; expected_aux=0; expected_storage=13;
        if(newfile("/V/D",15,0,13) || calls!=1 || bad ||
           pas[0]!=4 || strcmp((char*)pas+1,"/V/D"))return 3;
    }
    return 0;
}
'''


class FileCreate(unittest.TestCase):
    def test_native_request_and_error_sequences(self):
        with tempfile.TemporaryDirectory(prefix='file-create-') as d:
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
