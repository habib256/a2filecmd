"""Run the shared publication/rollback code on both CPUs with rename faults."""
import os
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


REPLACE_C = r'''
#include <stdio.h>
#include <string.h>
#pragma static-locals(on)
#define PATH_LEN 64
static unsigned char copy[512], present[3], data[3][4], mode, stopped;
static unsigned char renames, removes, polls, storage;
static unsigned char parent_length=2;
static char target[PATH_LEN],temporary[PATH_LEN];
static char note[80];
static unsigned char mli(unsigned char,void*);
static int discard(const char*);
static struct {
    unsigned char* copy_buf;
    char* note;
    size_t (*strlen)(const char*);
    char* (*strcpy)(char*,const char*);
    void* (*memcpy)(void*,const void*,size_t);
    unsigned char (*mli)(unsigned char,void*);
    int (*remove)(const char*);
} T;
static unsigned char cancelled(void) { ++polls;return stopped; }
#define REPLACE_CANCEL() cancelled()
#include "src/plugins/replace.h"
static unsigned char index_of(const unsigned char* p) {
    return p[p[0]]=='K'?2:p[p[0]]=='N'?1:0;
}
static unsigned char mli(unsigned char cmd,void* block) {
    unsigned char from=index_of(replace_ip.path),to;
    (void)block;
    if(cmd==0xC4) {
        if((mode==1 && !from) || (mode==2 && from==2))stopped=1;
        if((mode==7 && !from) || (mode==8 && from==2))return 0x27;
        memset(replace_ip.result,0,15);
        replace_ip.result[0]=mode==9?1:0xC3;
        replace_ip.result[4]=storage;
        return present[from]?0:0x46;
    }
    if(cmd!=0xC2)return 0x01;
    from=index_of(replace_rn.old);to=index_of(replace_rn.newpath);++renames;
    if(mode==3 && renames==1)stopped=1; /* after transaction starts: finish safely */
    if((mode==4 || mode==5) && from==1)return 0x27;
    if(mode==5 && from==2)return 0x27;
    if(present[to])return 0x47;
    memcpy(data[to],data[from],4);memset(data[from],0,4);
    present[to]=1;present[from]=0;return 0;
}
static int discard(const char* path) {
    (void)path;++removes;
    if(mode==6)return -1;
    present[2]=0;memset(data[2],0,4);return 0;
}
static unsigned char run(unsigned char fault,unsigned char kind,
                         unsigned char expected,unsigned char rn,unsigned char rm) {
    static const unsigned char old[4]={'O',0,0x80,0xFF},new[4]={'N',0x7F,0,0x42};
    unsigned char result,i;
    mode=fault;storage=kind;stopped=renames=removes=polls=0;
    present[0]=present[1]=1;present[2]=fault==11;
    memcpy(data[0],old,4);memcpy(data[1],new,4);memset(data[2],0,4);
    for(i=0;i<parent_length;++i)target[i]='A';
    target[0]='/';target[parent_length]='/';target[parent_length+1]='T';target[parent_length+2]=0;
    strcpy(temporary,target);temporary[parent_length+1]='N';
    result=replace_commit(temporary,target);
    if(result!=expected || renames!=rn || removes!=rm)return 0;
    if(expected==REPLACE_DONE || expected==REPLACE_BACKUP) {
        if(memcmp(data[0],new,4) || present[1])return 0;
        if(expected==REPLACE_BACKUP && memcmp(data[2],old,4))return 0;
    } else if(expected==REPLACE_RESTORE_FAILED) {
        if(present[0] || memcmp(data[1],new,4) || memcmp(data[2],old,4))return 0;
    } else if(memcmp(data[0],old,4) || memcmp(data[1],new,4))return 0;
    if((fault==1 || fault==2) && polls!=1)return 0;
    if(fault==3 && (polls!=1 || !stopped))return 0;
    return 1;
}
int main(void) {
    unsigned char i,kind;
    T.copy_buf=copy;T.note=note;T.strlen=strlen;T.strcpy=strcpy;T.memcpy=memcpy;
    T.mli=mli;T.remove=discard;
    for(i=0;i<3;++i) {
        if(!run(0,1,REPLACE_DONE,2,1))return 1;
        if(!run(1,1,REPLACE_CANCELLED,0,0))return 2;
        if(!run(2,1,REPLACE_CANCELLED,0,0))return 3;
        if(!run(3,1,REPLACE_DONE,2,1))return 4;
        if(!run(4,1,REPLACE_FAILED,3,0))return 5;
        if(!run(5,1,REPLACE_RESTORE_FAILED,3,0))return 6;
        if(!run(6,1,REPLACE_BACKUP,2,1))return 7;
        if(!run(7,1,REPLACE_FAILED,0,0))return 8;
        if(!run(8,1,REPLACE_REFUSED,0,0))return 9;
        if(!run(9,1,REPLACE_REFUSED,0,0))return 10;
        if(!run(11,1,REPLACE_REFUSED,0,0))return 11;
        for(kind=0;kind<16;++kind)
            if(!run(0,kind,kind>=1 && kind<=3?REPLACE_DONE:REPLACE_REFUSED,
                    kind>=1 && kind<=3?2:0,kind>=1 && kind<=3?1:0))return 12;
        if(!run(0,255,REPLACE_REFUSED,0,0))return 13;
        parent_length=53;if(!run(0,1,REPLACE_DONE,2,1))return 14;
        parent_length=54;if(!run(0,1,REPLACE_REFUSED,0,0))return 15;
        parent_length=2;
    }
    return 0;
}
'''


class FileInstall(unittest.TestCase):
    def test_native_replace_cancellation_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix='replace-native-') as directory:
            p=Path(directory);source=p/'test.c';source.write_text(REPLACE_C)
            for cpu in ('sim6502','sim65c02'):
                with self.subTest(cpu=cpu):
                    compiler,simulator=shutil.which('cl65'),shutil.which('sim65')
                    env=os.environ.copy()
                    head=Path(env.get('CC65_HEAD',str(Path.home()/'opt/cc65-head')))
                    if cpu=='sim6502' and (head/'bin/cl65').exists():
                        compiler,simulator=str(head/'bin/cl65'),str(head/'bin/sim65')
                        env['CC65_HOME']=str(head/'share/cc65')
                    result=subprocess.run([compiler,'-t',cpu,'-O','-Oirs','-Cl',
                                           '-I',str(ROOT),'-o',str(p/'test'),str(source)],
                                          capture_output=True,text=True,env=env)
                    self.assertEqual(result.returncode,0,result.stderr)
                    run=subprocess.run([simulator,str(p/'test')],capture_output=True,timeout=15,env=env)
                    self.assertEqual(run.returncode,0,run.stderr)

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
