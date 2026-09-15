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
static unsigned char copy_buf[512], active, efresh, edirty, econv;
static char edit_buf[6144];
#define EDIT_BUF edit_buf
static unsigned int elen, etype, eaux, a2fc_ops;
static long text_starts[80];
static unsigned int progress_skipped, progress_done, progress_abort, over_policy=1;
static int fault, fired, rename_calls, output_open;
static int confirms;
static const char ed_convert[] = "Save converted text?";
static unsigned char confirm(const char* text) {++confirms;strcpy(message_text,text);return fault!=97;}
static FILE* output;
static FILE* input;
static unsigned char old_bytes[4096];
static char old_path[64];
static size_t old_size;
static int old_exists, copy_mode, copy_closes;
static void snapshot_destination(const char* p) {
    FILE* f;strcpy(old_path,p);copy_mode=1;copy_closes=0;
    f=fopen(p,"rb");old_exists=f!=NULL;old_size=0;
    if(f){old_size=fread(old_bytes,1,sizeof old_bytes,f);fclose(f);}
}
static void check_old_destination(void) {
    FILE* f;unsigned char b[4096];size_t n;
    if(!copy_mode)return;
    f=fopen(old_path,"rb");
    if(!old_exists){if(f)abort();return;}
    if(!f)abort();n=fread(b,1,sizeof b,f);fclose(f);
    if(n!=old_size || memcmp(b,old_bytes,n))abort();
}
static char checked_path[64];
static unsigned char file_info(const char* path) {
    struct stat st;
    strcpy(checked_path,path);
    if(fault==7 || (fault==30 && !strcmp(path,full))) {_oserror=0x27;return 0;}
    if(stat(path,&st)) {_oserror=errno==ENOENT?0x46:0x27;return 0;}
    gfi[3]=(fault==15 || fault==31)?1:0xC3;gfi[4]=S_ISDIR(st.st_mode)?15:6;_oserror=0;return 1;
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
    if(fault==20){errno=EIO;return -1;}
    if(fault==11 && !fired++) {f=fopen(path,"wb");fputs("new arrival",f);fclose(f);}
    return open(path,flags,0600);
}
#define open reserve_file
static int close_reservation(int fd) {
    int r=close(fd);
    return fault==18 || fault==19 ? -1 : r;
}
#define close close_reservation
static void message(const char* s) {snprintf(message_text,sizeof message_text,"%s",s);}
static void report_error(const char* s) {message(s);}
static void too_long(void) {message("Path too long");}
static void clear_row(int r) {}
static void question_begin(void) {}
static void revers(int r) {}
static void gotoxy(int x,int y) {}
#define cprintf(...) ((void)0)
static char cgetc(void) {return 'o';}
static void progress_bar(const char* s,unsigned long d,unsigned long t) {}
static unsigned char abort_key(void) {if(fault==16 || fault==23)progress_abort=1;return progress_abort;}
static unsigned char overlay(const char* s) {strcpy(other_full,"/overlay/clobbered");return fault!=17;}
static unsigned char push_name(char* p,const char* n) {
    if(strlen(p)+strlen(n)+1>=PATH_LEN)return 0;strcat(p,"/");strcat(p,n);return 1;
}
static FILE* open_file(const char* p,const char* mode) {
    FILE* f;
    if((fault==18 || fault==19) && !strcmp(mode,"wb"))abort();
    if((fault==12 || fault==25) && !strcmp(mode,"wb"))return NULL;
    f=fopen(p,mode);
    if(!strcmp(mode,"wb")){output=f;output_open=1;}
    else if(!strcmp(p,full)) input=f;
    else if(fault==13 && !strcmp(mode,"rb")){if(f)fclose(f);return NULL;}
    return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    if(fault==28 && ftell(f)>=512){fired=1;return 0;}
    if(fault==1 && f==input && ftell(f)>=256){fired=1;return 0;}
    return fread(p,s,n,f);
}
static int error_file(FILE* f) {return ((fault==37 || fault==38) && fired && output_open && f==output)||(fault==28 && fired)||(fault==1 && fired && f==input)||ferror(f);}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f) {
    unsigned char damaged[6144];
    check_old_destination();
    if(fault==37 || fault==38)fired=1; /* Full count with the stream error flag set. */
    if(fault==2 || fault==21)return 0;
    if(fault==4 && n){memcpy(damaged,p,n);damaged[n-1]^=1;return fwrite(damaged,s,n,f);}
    return fwrite(p,s,n,f);
}
static int close_file(FILE* f) {
    int is_output=output_open && f==output;
    check_old_destination();++copy_closes;
    int r=fclose(f);if(is_output)output_open=0;
    return ((fault==3 || fault==22) && is_output) || (fault==29 && !is_output)?-1:r;
}
static int seek_file(FILE* f,long p,int origin) {return fault==5?-1:fseek(f,p,origin);}
static int rename_file(const char* from,const char* to) {
    struct stat st;++rename_calls;
    if(copy_mode && !strcmp(from,old_path) && copy_closes!=(copy_mode==2?2:4))abort();
    if((fault==19 || (fault>=21 && fault<=25)) && strstr(from,"A2FC.BAK"))abort();
    if((fault==8 && strstr(from,"A2FC.EDIT")) || (fault==9 && (strstr(from,"A2FC.BAK") || strstr(from,"A2FC.COPY"))))return -1;
    if(fault==26 && strstr(from,"A2FC.COPY")) {
        FILE* f=fopen(to,"wx");if(!f)abort();fputs("late arrival",f);fclose(f);
    }
    if(fault==27 && strstr(from,"A2FC.COPY"))return -1;
    if(fault==32 && strstr(to,"A2FC.ED.BAK"))return -1;
    if(fault==33 && (strstr(from,"A2FC.EDIT") || strstr(from,"A2FC.ED.BAK")))return -1;
    if(fault==34 && strstr(from,"A2FC.EDIT")) {
        FILE* f=fopen(to,"wx");if(!f)abort();fputs("late arrival",f);fclose(f);
    }
    if(fault==35 && strstr(to,"A2FC.ED.BAK")) {
        FILE* f=fopen(to,"wx");if(!f)abort();fputs("late backup",f);fclose(f);
    }
    if(fault==36 && strstr(to,"A2FC.ED.BAK"))return -1;
    if(!stat(to,&st))return -1;
    return rename(from,to);
}
static int remove_file(const char* p) {
    if(fault==19 || fault==38 || (fault>=21 && fault<=25) || (fault>=28 && fault<=32))return -1;
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
''' + (ROOT / 'src/file_output.h').read_text() + (ROOT / 'src/file_copy.h').read_text() + section('static const char ed_safety_0', '/* E: edits the file') + r'''
#undef fopen
#undef fread
#undef fclose
int main(int argc,char**argv) {
    unsigned char r;
    strcpy(full,argv[2]);strcpy(other_full,argv[3]);fault=atoi(argv[4]);
    if(argv[1][0]=='e') {
        FILE* f=fopen(full,"rb");elen=fread(EDIT_BUF,1,sizeof edit_buf,f);fclose(f);
        memset(EDIT_BUF,'N',elen);edirty=1;etype=6;eaux=0;
        if(!strcmp(argv[1],"editfresh")){unlink(full);efresh=1;}
        if(!strcmp(argv[1],"editnoop"))edirty=0;          /* nothing typed */
        if(!strcmp(argv[1],"editconv"))econv=1;           /* bit 7 or LF changed on loading */
        snapshot_destination(full);copy_mode=2;
        r=edit_save();
        if(!r && fault!=97 && econv)abort();
        if(!r) {
            unsigned int i;
            if(!edirty)abort();
            for(i=0;i<elen;++i)if(EDIT_BUF[i]!='N')abort();
        }
    } else { snapshot_destination(other_full);r=copy_file("DATA",6,0); }
    if(argv[1][0]=='s') {
        /* The operation boundary resets cancellation, but deliberately
         * leaves CopyState and the shared buffers dirty for the next copy. */
        printf("first=%u\n", r);
        fault=atoi(argv[6]); fired=0; progress_abort=0;
        strcpy(other_full,argv[5]);
        snapshot_destination(other_full);
        r=copy_file("DATA",6,0);
    }
    printf("%u %u %s\nconfirms=%d\n",r,edirty,message_text,confirms);
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
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT/'src'), str(cls.root/'test.c'), '-o', str(cls.exe)], check=True, capture_output=True)

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

    def test_full_write_count_with_stream_error_preserves_originals(self):
        for mode in ('copy','edit'):
            with self.subTest(mode=mode):
                result,out=self.run_op(mode,37)
                self.assertEqual(result,0)
                self.assertEqual(self.src.read_bytes(),self.original)
                self.assertEqual(self.dst.read_bytes(),self.previous)
                if mode=='edit':self.assertEqual(out.split()[1],'1')
                for name in ('A2FC.COPY','A2FC.BAK','A2FC.EDIT','A2FC.ED.BAK'):
                    self.assertFalse((self.p/name).exists())

    def test_write_error_and_cleanup_failure_keep_recovery_bytes(self):
        for mode,temp,expected in (('copy','A2FC.COPY',self.original),
                                   ('edit','A2FC.EDIT',b'N'*len(self.original))):
            with self.subTest(mode=mode):
                result,out=self.run_op(mode,38)
                self.assertEqual(result,0)
                self.assertEqual(self.src.read_bytes(),self.original)
                self.assertEqual(self.dst.read_bytes(),self.previous)
                self.assertEqual((self.p/temp).read_bytes(),expected)
                self.assertIn('Cleanup failed' if mode=='copy' else 'recover A2FC.EDIT',out)
                self.assertEqual(self.run_op(mode)[0],0)
                self.assertEqual((self.p/temp).read_bytes(),expected)
                self.assertEqual(self.src.read_bytes(),self.original)
                self.assertEqual(self.dst.read_bytes(),self.previous)

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
        self.assertFalse(self.dst.exists())
        self.assertEqual((self.p/'A2FC.COPY').read_bytes(),b'new arrival')

    def test_reservation_close_failure_never_reopens_for_writing(self):
        self.assertEqual(self.run_op(fault=18)[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_reservation_close_and_cleanup_failure_preserve_original(self):
        result,note=self.run_op(fault=19)
        self.assertEqual(result,0)
        self.assertIn('Cleanup failed',note)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual((self.p/'A2FC.COPY').read_bytes(),b'')
        self.assertFalse((self.p/'A2FC.BAK').exists())
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual((self.p/'A2FC.COPY').read_bytes(),b'')
        self.assertEqual(self.src.read_bytes(),self.original)

    def test_failed_exclusive_create_restores_previous_destination(self):
        self.assertEqual(self.run_op(fault=20)[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_failed_cleanup_never_restores_over_remaining_output(self):
        for existing in (False,True):
            for fault,expected in ((21,b''),(22,self.original),
                                   (23,self.original[:512]),(25,b'')):
                with self.subTest(existing=existing,fault=fault):
                    bak=self.p/'A2FC.BAK'
                    bak.unlink(missing_ok=True)
                    tmp=self.p/'A2FC.COPY';tmp.unlink(missing_ok=True)
                    if existing:self.dst.write_bytes(self.previous)
                    else:self.dst.unlink(missing_ok=True)
                    result,note=self.run_op(fault=fault)
                    self.assertEqual(result,0)
                    self.assertIn('Cleanup failed',note)
                    self.assertEqual(self.src.read_bytes(),self.original)
                    self.assertEqual(tmp.read_bytes(),expected)
                    if existing:self.assertEqual(self.dst.read_bytes(),self.previous)
                    else:self.assertFalse(self.dst.exists())
                    self.assertFalse(bak.exists())

    def test_install_failure_restores_original_and_keeps_verified_temporary(self):
        self.assertEqual(self.run_op(fault=27)[0],0)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual((self.p/'A2FC.COPY').read_bytes(),self.original)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_late_install_collision_preserves_all_three_files(self):
        self.assertEqual(self.run_op(fault=26)[0],0)
        self.assertEqual(self.dst.read_bytes(),b'late arrival')
        self.assertEqual((self.p/'A2FC.BAK').read_bytes(),self.previous)
        self.assertEqual((self.p/'A2FC.COPY').read_bytes(),self.original)
        self.assertEqual(self.src.read_bytes(),self.original)

    def test_existing_temporary_is_never_overwritten(self):
        tmp=self.p/'A2FC.COPY';tmp.write_bytes(b'recovery bytes')
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(tmp.read_bytes(),b'recovery bytes')
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual(self.src.read_bytes(),self.original)

    def test_temporary_aliasing_source_is_never_removed(self):
        reserved=self.p/'A2FC.COPY';self.src.rename(reserved);self.src=reserved
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual(self.dst.read_bytes(),self.previous)

    def test_target_equal_to_temporary_is_refused(self):
        self.dst=self.p/'A2FC.COPY';self.dst.write_bytes(self.previous)
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual(self.src.read_bytes(),self.original)

    def test_temporary_path_overflow_refuses_before_writing(self):
        directory=self.p/('D'*(61-len(str(self.p))-1));directory.mkdir()
        self.dst=directory/'X';self.assertEqual(len(str(self.dst)),63)
        self.dst.write_bytes(self.previous)
        self.assertEqual(self.run_op()[0],0)
        self.assertEqual(self.dst.read_bytes(),self.previous)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual([p.name for p in directory.iterdir()],['X'])

    def test_empty_and_exact_block_copies_publish_after_verification(self):
        for size in (0,256,512,1024):
            with self.subTest(size=size):
                data=bytes(range(256))*(size//256);self.src.write_bytes(data)
                self.assertEqual(self.run_op()[0],1)
                self.assertEqual(self.dst.read_bytes(),data)
                self.assertEqual(self.src.read_bytes(),data)
                self.assertFalse((self.p/'A2FC.COPY').exists())
                self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_cancel_then_copy_reinitializes_borrowed_state(self):
        next_dst = self.p/'NEXT'
        next_dst.write_bytes(b'next original')
        out = subprocess.check_output([self.exe, 'sequence', self.src, self.dst,
                                       '16', next_dst, '0'], text=True).splitlines()
        self.assertEqual(out[0], 'first=0')
        self.assertEqual(out[1].split()[0], '1')
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual(self.dst.read_bytes(), self.previous)
        self.assertEqual(next_dst.read_bytes(), self.original)
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_failed_overlay_after_success_cannot_reuse_verified_state(self):
        next_dst = self.p/'NEXT'
        next_dst.write_bytes(b'next original')
        out = subprocess.check_output([self.exe, 'sequence', self.src, self.dst,
                                       '0', next_dst, '17'], text=True).splitlines()
        self.assertEqual(out[0], 'first=1')
        self.assertEqual(out[1].split()[0], '0')
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual(self.dst.read_bytes(), self.original)
        self.assertEqual(next_dst.read_bytes(), b'next original')
        self.assertFalse((self.p/'A2FC.BAK').exists())

    def test_editor_save_without_changes_leaves_the_file_alone(self):
        before = sorted(q.name for q in self.p.iterdir())
        result, out = self.run_op('editnoop')
        self.assertEqual(result, 1)
        self.assertIn('confirms=0', out)
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual(sorted(q.name for q in self.p.iterdir()), before)

    def test_editor_converted_text_is_saved_only_when_confirmed(self):
        before = sorted(q.name for q in self.p.iterdir())
        result, out = self.run_op('editconv', 97)
        self.assertEqual(result, 0)
        self.assertIn('confirms=1', out)
        self.assertEqual(self.src.read_bytes(), self.original)
        self.assertEqual(sorted(q.name for q in self.p.iterdir()), before)
        result, out = self.run_op('editconv')
        self.assertEqual(result, 1)
        self.assertIn('confirms=1', out)
        self.assertEqual(self.src.read_bytes(), b'N'*len(self.original))

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

    def test_editor_cleanup_failures_report_recovery_and_keep_original(self):
        for fault in (19,21,22,25,28,29,30,31,32):
            with self.subTest(fault=fault):
                result,out=self.run_op('edit',fault)
                self.assertEqual(result,0)
                self.assertIn('recover A2FC.EDIT / A2FC.ED.BAK',out)
                self.assertEqual(self.src.read_bytes(),self.original)
                temp=self.p/'A2FC.EDIT'
                expected=b'' if fault in (19,21,25) else b'N'*len(self.original)
                self.assertEqual(temp.read_bytes(),expected)
                self.assertFalse((self.p/'A2FC.ED.BAK').exists())
                # A subsequent save must not truncate or remove recovery data.
                self.assertEqual(self.run_op('edit')[0],0)
                self.assertEqual(temp.read_bytes(),expected)
                self.assertEqual(self.src.read_bytes(),self.original)
                temp.unlink()

    def test_editor_reservation_failures_and_late_collision(self):
        for fault in (18,20,11):
            with self.subTest(fault=fault):
                self.assertEqual(self.run_op('edit',fault)[0],0)
                self.assertEqual(self.src.read_bytes(),self.original)
                temp=self.p/'A2FC.EDIT'
                if fault==11:
                    self.assertEqual(temp.read_bytes(),b'new arrival')
                    temp.unlink()
                else:
                    self.assertFalse(temp.exists())
                self.assertFalse((self.p/'A2FC.ED.BAK').exists())

    def test_editor_install_failure_restores_original_and_keeps_temporary(self):
        self.assertEqual(self.run_op('edit',8)[0],0)
        self.assertEqual(self.src.read_bytes(),self.original)
        self.assertEqual((self.p/'A2FC.EDIT').read_bytes(),b'N'*len(self.original))

    def test_editor_failed_restore_keeps_verified_temp_and_original_backup(self):
        result,out=self.run_op('edit',33)
        self.assertEqual(result,0)
        self.assertIn('Restore failed',out)
        self.assertFalse(self.src.exists())
        self.assertEqual((self.p/'A2FC.ED.BAK').read_bytes(),self.original)
        self.assertEqual((self.p/'A2FC.EDIT').read_bytes(),b'N'*len(self.original))

    def test_editor_late_target_collision_preserves_all_versions(self):
        result,out=self.run_op('edit',34)
        self.assertEqual(result,0)
        self.assertIn('Restore failed',out)
        self.assertEqual(self.src.read_bytes(),b'late arrival')
        self.assertEqual((self.p/'A2FC.ED.BAK').read_bytes(),self.original)
        temp=self.p/'A2FC.EDIT'
        self.assertEqual(temp.read_bytes(),b'N'*len(self.original))
        self.assertEqual(self.run_op('edit')[0],0)
        self.assertEqual(self.src.read_bytes(),b'late arrival')
        self.assertEqual(temp.read_bytes(),b'N'*len(self.original))
        self.assertEqual((self.p/'A2FC.ED.BAK').read_bytes(),self.original)

    def test_editor_backup_rename_failure_retains_verified_temp(self):
        for fault in (35,36):
            with self.subTest(fault=fault):
                result,out=self.run_op('edit',fault)
                self.assertEqual(result,0)
                self.assertIn('recover A2FC.EDIT',out)
                self.assertEqual(self.src.read_bytes(),self.original)
                temp=self.p/'A2FC.EDIT'
                self.assertEqual(temp.read_bytes(),b'N'*len(self.original))
                backup=self.p/'A2FC.ED.BAK'
                if fault==35:self.assertEqual(backup.read_bytes(),b'late backup')
                else:self.assertFalse(backup.exists())
                self.assertEqual(self.run_op('edit')[0],0)
                self.assertEqual(temp.read_bytes(),b'N'*len(self.original))
                self.assertEqual(self.src.read_bytes(),self.original)
                temp.unlink()
                if backup.exists():backup.unlink()

    def test_editor_installed_backup_cleanup_failure_reports_saved(self):
        result,out=self.run_op('edit',10)
        self.assertEqual(result,1)
        self.assertEqual(out.split()[1],'0')
        self.assertIn('Saved; A2FC.ED.BAK retained',out)
        self.assertEqual(self.src.read_bytes(),b'N'*len(self.original))
        self.assertEqual((self.p/'A2FC.ED.BAK').read_bytes(),self.original)
        self.assertFalse((self.p/'A2FC.EDIT').exists())

    def test_editor_fresh_install_and_late_collision(self):
        self.assertEqual(self.run_op('editfresh')[0],1)
        self.assertEqual(self.src.read_bytes(),b'N'*len(self.original))
        result,out=self.run_op('editfresh',34)
        self.assertEqual(result,0)
        self.assertNotIn('Restore failed',out)
        self.assertIn('recover A2FC.EDIT',out)
        self.assertEqual(self.src.read_bytes(),b'late arrival')
        self.assertEqual((self.p/'A2FC.EDIT').read_bytes(),b'N'*len(self.original))
        self.assertFalse((self.p/'A2FC.ED.BAK').exists())

    def test_editor_preserves_existing_temporary_and_backup(self):
        for name in ('A2FC.EDIT','A2FC.ED.BAK'):
            with self.subTest(name=name):
                saved=self.p/name;saved.write_bytes(b'previous recovery')
                self.assertEqual(self.run_op('edit')[0],0)
                self.assertEqual(saved.read_bytes(),b'previous recovery')
                self.assertEqual(self.src.read_bytes(),self.original)
                saved.unlink()

if __name__ == '__main__': unittest.main()
