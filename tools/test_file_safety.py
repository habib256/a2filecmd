"""Execute the real core copy/save routines with failing filesystem operations.

The mock ProDOS RENAME refuses existing names. Every case checks persisted
bytes, including backups, not just the return value or UI message.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()

def section(start, end):
    return SOURCE[SOURCE.index(start):SOURCE.index(end, SOURCE.index(start))]

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#define PATH_LEN 64
#define KEY_ESC 27
#define OVERWRITE_ALL 1
#define SKIP_ALL 2
static unsigned char gfi[18], _oserror, _filetype;
static unsigned int _auxtype;
static char full[64], other_full[64], message_text[100];
static unsigned char copy_buf[512], active, efresh, edirty;
static char edit_buf[6144];
#define EDIT_BUF edit_buf
static unsigned int elen, etype, eaux, a2fc_ops;
static long text_starts[80];
static unsigned int progress_skipped, progress_done, progress_abort, over_policy=1;
static int fault, fired, rename_calls, output_open;
static FILE* output;
static FILE* input;
static char checked_path[64];
static unsigned char file_info(const char* path) {
    struct stat st;
    strcpy(checked_path,path);
    if(fault==7) {_oserror=0x27;return 0;}
    if(stat(path,&st)) {_oserror=errno==ENOENT?0x46:0x27;return 0;}
    gfi[3]=(fault==15)?1:0xC3;gfi[4]=S_ISDIR(st.st_mode)?15:6;_oserror=0;return 1;
}
static unsigned char exists(const char* p) {return file_info(p);}
static unsigned char mli_call(unsigned char cmd,void* params) {
    FILE* f;
    if(cmd!=0xC0 || gfi[0]!=7 || gfi[3]!=0xC3 || gfi[7]!=1)abort();
    if(fault==11 && !fired++) {f=fopen(checked_path,"wb");fputs("new arrival",f);fclose(f);}
    f=fopen(checked_path,"wx");if(!f)return 0x47;fclose(f);return 0;
}
static int reserve_file(const char* path,int flags) {
    FILE* f;
    if((flags & (O_CREAT|O_EXCL))!=(O_CREAT|O_EXCL))abort();
    if(fault==11 && !fired++) {f=fopen(path,"wb");fputs("new arrival",f);fclose(f);}
    return open(path,flags,0600);
}
#define open reserve_file
static void message(const char* s) {snprintf(message_text,sizeof message_text,"%s",s);}
static void report_error(const char* s) {message(s);}
static void too_long(void) {message("Path too long");}
static void clear_row(int r) {}
static void gotoxy(int x,int y) {}
#define cprintf(...) ((void)0)
static char cgetc(void) {return 'o';}
static void progress_bar(const char* s,unsigned long d,unsigned long t) {}
static unsigned char abort_key(void) {if(fault==16)progress_abort=1;return progress_abort;}
static unsigned char overlay(const char* s) {strcpy(other_full,"/overlay/clobbered");return fault!=17;}
static unsigned char push_name(char* p,const char* n) {
    if(strlen(p)+strlen(n)+1>=PATH_LEN)return 0;strcat(p,"/");strcat(p,n);return 1;
}
static FILE* open_file(const char* p,const char* mode) {
    FILE* f;
    if(fault==12 && !strcmp(mode,"wb"))return NULL;
    f=fopen(p,mode);
    if(!strcmp(mode,"wb")){output=f;output_open=1;}
    else if(!strcmp(p,full)) input=f;
    else if(fault==13 && !strcmp(mode,"rb")){if(f)fclose(f);return NULL;}
    return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    if(fault==1 && f==input && ftell(f)>=256){fired=1;return 0;}
    return fread(p,s,n,f);
}
static int error_file(FILE* f) {return (fault==1 && fired && f==input)||ferror(f);}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f) {
    unsigned char damaged[6144];
    if(fault==2 || fault==9)return 0;
    if(fault==4 && n){memcpy(damaged,p,n);damaged[n-1]^=1;return fwrite(damaged,s,n,f);}
    return fwrite(p,s,n,f);
}
static int close_file(FILE* f) {
    int is_output=output_open && f==output;
    int r=fclose(f);if(is_output)output_open=0;
    return fault==3 && is_output?-1:r;
}
static int seek_file(FILE* f,long p,int origin) {return fault==5?-1:fseek(f,p,origin);}
static int rename_file(const char* from,const char* to) {
    struct stat st;++rename_calls;
    if((fault==8 && strstr(from,"A2FC.EDIT")) || (fault==9 && strstr(from,"A2FC.BAK")))return -1;
    if(!stat(to,&st))return -1;
    return rename(from,to);
}
static int remove_file(const char* p) {
    if(fault==10 && (strstr(p,"A2FC.BAK")||strstr(p,"A2FC.ED.BAK")))return -1;
    return remove(p);
}
#define fopen open_file
#define fread read_file
#define ferror error_file
#define fwrite write_file
#define fclose close_file
#define fseek seek_file
#define rename rename_file
#define remove remove_file
''' + section('static FILE* new_output(const char* path)\n{', '/* Rewrites access, type and auxtype') + section('struct CopyState {', '/* The three tree walks') + section('static const char ed_safety_0', '/* E: edits the file') + r'''
#undef fopen
#undef fread
#undef fclose
int main(int argc,char**argv) {
    unsigned char r;
    strcpy(full,argv[2]);strcpy(other_full,argv[3]);fault=atoi(argv[4]);
    if(argv[1][0]=='e') {
        FILE* f=fopen(full,"rb");elen=fread(EDIT_BUF,1,sizeof edit_buf,f);fclose(f);
        memset(EDIT_BUF,'N',elen);edirty=1;etype=6;eaux=0;
        r=edit_save();
    } else r=copy_file("DATA",6,0);
    printf("%u %u %s\n",r,edirty,message_text);
    return 0;
}
'''

class FileSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='a2safe-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        (cls.root/'test.c').write_text(HARNESS)
        cls.exe = cls.root/'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', str(cls.root/'test.c'), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix='io-', dir=self.root)
        self.addCleanup(self.case.cleanup)
        self.p = Path(self.case.name)
        self.src = self.p/'SRC'
        self.dst = self.p/'DST'
        self.original = b'Source\r' * 150
        self.previous = b'Previous destination\r' * 100
        self.src.write_bytes(self.original)
        self.dst.write_bytes(self.previous)

    def run_op(self, mode='copy', fault=0):
        out = subprocess.check_output([self.exe, mode, self.src, self.dst, str(fault)], text=True)
        return int(out.split()[0]), out

    def test_copy_success_is_verified_and_preserves_source(self):
        self.assertEqual(self.run_op()[0], 1)
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual(self.dst.read_bytes(), self.original)
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_copy_failures_restore_old_destination(self):
        for fault in (1,2,3,4,5,7,12,13,15,16):
            with self.subTest(fault=fault):
                self.assertEqual(self.run_op(fault=fault)[0], 0)
                self.assertEqual(self.src.read_bytes(), self.original)
                self.assertEqual(self.dst.read_bytes(), self.previous)

    def test_failed_restore_keeps_recoverable_backup(self):
        self.assertEqual(self.run_op(fault=9)[0], 0)
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual((self.p/'A2FC.BAK').read_bytes(), self.previous)

    def test_existing_backup_is_never_overwritten(self):
        bak=self.p/'A2FC.BAK';bak.write_bytes(b'recover me')
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(bak.read_bytes(),b'recover me')
        self.assertEqual(self.dst.read_bytes(),self.previous)

    def test_unverified_copy_never_reports_move_safe(self):
        self.assertEqual(self.run_op(fault=17)[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual(self.dst.read_bytes(),self.previous)

    def test_cleanup_failure_keeps_both_versions_and_source(self):
        self.assertEqual(self.run_op(fault=10)[0],0)
        self.assertEqual(self.dst.read_bytes(),self.original)
        self.assertEqual((self.p/'A2FC.BAK').read_bytes(),self.previous)
        self.assertEqual(self.src.read_bytes(),self.original)

    def test_new_arrival_is_not_truncated_or_removed(self):
        self.dst.unlink()
        self.assertEqual(self.run_op(fault=11)[0],0)
        self.assertEqual(self.dst.read_bytes(),b'new arrival')

    def test_editor_save_verifies_and_installs(self):
        self.assertEqual(self.run_op('edit')[0],1)
        self.assertEqual(self.src.read_bytes(),b'N'*len(self.original))

    def test_editor_errors_keep_original_and_dirty_buffer(self):
        for fault in (2,3,4,7,12,13,15):
            with self.subTest(fault=fault):
                result,out=self.run_op('edit',fault)
                self.assertEqual(result,0)
                self.assertEqual(out.split()[1],'1')
                self.assertEqual(self.src.read_bytes(),self.original)

    def test_editor_install_failure_restores_original_and_keeps_temporary(self):
        self.assertEqual(self.run_op('edit',8)[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual((self.p/'A2FC.EDIT').read_bytes(),b'N'*len(self.original))

    def test_editor_preserves_existing_temporary_and_backup(self):
        for name in ('A2FC.EDIT','A2FC.ED.BAK'):
            with self.subTest(name=name):
                saved=self.p/name;saved.write_bytes(b'previous recovery')
                self.assertEqual(self.run_op('edit')[0],0)
                self.assertEqual(saved.read_bytes(),b'previous recovery')
                self.assertEqual(self.src.read_bytes(),self.original)
                saved.unlink()

if __name__ == '__main__': unittest.main()
