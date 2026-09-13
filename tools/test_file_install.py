"""Run the shared publication/rollback code on both CPUs with rename faults."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = r'''
#include <string.h>
#pragma static-locals(on)
/* The three entries contain distinct bytes, not just existence flags. */
static unsigned char data[3], mode, calls;
static unsigned char rename_file(const char* from, const char* to) {
    unsigned char f=from[0]-'0', t=to[0]-'0';
    ++calls;
    if(mode==1 && calls==1)return 0x27;
    if((mode==2 || mode==3) && f==1)return 0x27;
    if(mode==3 && f==2)return 0x27;
    if(mode==5 && f==1)data[t]='X';
    if(data[t])return 0x47;
    if(!data[f])return 0x46;
    data[t]=data[f];data[f]=0;return 0;
}
#define FI_RENAME rename_file
#include "src/plugins/file_install.h"
static unsigned char run(unsigned char exists, unsigned char fault,
                         unsigned char result, const char* expected,
                         unsigned char count) {
    data[0]=exists?'O':0;data[1]='N';data[2]=fault==4?'B':0;
    mode=fault;calls=0;
    return file_install("1","0","2",exists)==result &&
           !memcmp(data,expected,3) && calls==count;
}
int main(void) {
    unsigned char i;
    /* Repeat without clearing helper BSS, including success after rollback. */
    for(i=0;i<3;++i) {
        if(!run(1,0,FILE_INSTALLED,"N\0O",2))return 1;
        if(!run(1,1,FILE_INSTALL_FAILED,"ON\0",1))return 2;
        if(!run(1,2,FILE_INSTALL_FAILED,"ON\0",3))return 3;
        if(!run(1,3,FILE_RESTORE_FAILED,"\0NO",3))return 4;
        if(!run(1,4,FILE_INSTALL_FAILED,"ONB",1))return 5;
        if(!run(1,5,FILE_RESTORE_FAILED,"XNO",3))return 6;
        if(!run(0,0,FILE_INSTALLED,"N\0\0",1))return 7;
        if(!run(0,2,FILE_INSTALL_FAILED,"\0N\0",1))return 8;
        if(!run(0,5,FILE_INSTALL_FAILED,"XN\0",1))return 9;
    }
    return 0;
}
'''


class FileInstall(unittest.TestCase):
    def test_native_publication_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='file-install-') as d:
            p = Path(d)
            source = p / 'test.c'
            for bound in (False, True):
                code = C
                if bound:
                    code = code.replace('#define FI_RENAME rename_file',
                        'static struct { const char *temp,*target,*backup; unsigned char had_old; } '
                        'state={"1","0","2",0};\n#define FI_STATE (&state)\n#define FI_RENAME rename_file')
                    code = code.replace('file_install("1","0","2",exists)',
                                        '(state.had_old=exists,file_install())')
                source.write_text(code)
                for cpu in ('sim6502', 'sim65c02'):
                    with self.subTest(cpu=cpu, bound=bound):
                        result = subprocess.run(
                            [shutil.which('cl65'), '-t', cpu, '-O', '-Oirs', '-Cl',
                             '-I', str(ROOT), '-o', str(p / 'test'), str(source)],
                            capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        subprocess.run([shutil.which('sim65'), str(p / 'test')],
                                       check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
