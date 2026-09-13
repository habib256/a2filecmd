"""Run GOTO's actual configuration loader/save with combined I/O failures."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
#include <errno.h>
#include <sys/stat.h>
static char list_mem[585], text_mem[2001];
#define LIST list_mem
#define TEXT text_mem
static int read_status(FILE*);
#define ferror read_status
#include "src/plugins/goto.c"
#undef ferror
static int fault, opens, closes;
static FILE* failed_read;
static int read_status(FILE* f) { return f==failed_read || ferror(f); }
static FILE* open_file(const char* p,const char* mode) {
    ++opens;
    if(((fault==1 || fault==2) && opens==1) || (fault==13 && opens==3))return NULL;
    return fopen(p,mode);
}
static size_t read_file(void* p,size_t z,size_t n,FILE* f) {
    if(fault==3 && opens==1) {failed_read=f;return fread(p,z,7,f);}
    if(fault==14 && opens==3 && n>1)return fread(p,z,n-1,f);
    if(fault==15 && opens==3 && n==1){failed_read=f;return 0;}
    return fread(p,z,n,f);
}
static size_t write_file(const void* p,size_t z,size_t n,FILE* f) {
    char damaged[2001];
    if(fault==10 || fault==20)return fwrite(p,z,n/2,f);
    if(fault==11){memcpy(damaged,p,n);damaged[0]^=1;return fwrite(damaged,z,n,f);}
    return fwrite(p,z,n,f);
}
static int close_file(FILE* f) {
    int r=fclose(f);++closes;
    return ((fault==4 && closes==1) || ((fault==12 || fault==21) && closes==2) ||
            (fault==16 && closes==3)) ? EOF : r;
}
static void decode(char* out,const char* p){memcpy(out,p+1,(unsigned char)p[0]);out[(unsigned char)p[0]]=0;}
static unsigned char file_call(unsigned char cmd,void* unused) {
    char from[81],to[81];struct stat st;FILE* f;
    (void)unused;
    if(cmd==0xC2) {
        decode(from,ren.from);decode(to,ren.to);
        if((fault==17 || fault==18) && strstr(from,"GOTO.TMP"))return 0x27;
        if(fault==18 && strstr(from,"GOTO.BAK"))return 0x27;
        if(fault==27 && strstr(from,"GOTO.CFG"))return 0x27;
        if((fault==28 && strstr(from,"GOTO.TMP")) ||
           (fault==29 && strstr(to,"GOTO.BAK"))) {
            f=fopen(to,"wx");if(!f)abort();fputs("late arrival",f);fclose(f);
        }
        if(!stat(to,&st))return 0x47;
        return rename(from,to)?(errno==ENOENT?0x46:0x27):0;
    }
    decode(from,info.path);
    if(cmd==0xC4) {
        if(fault==2 || (fault==22 && strstr(from,"GOTO.BAK")) ||
           (fault==23 && strstr(from,"GOTO.CFG")))return 0x27;
        memset(info.fields,0,15);info.fields[0]=fault==24?0x81:0xE3;
        info.fields[4]=fault==25?0:fault==26?13:1;
        return stat(from,&st)?(errno==ENOENT?0x46:0x27):0;
    }
    if(cmd==0xC0){f=fopen(from,"wx");if(!f)return errno==EEXIST?0x47:0x27;return fclose(f)?0x27:0;}
    if(cmd==0xC1){
        if((fault==19 && strstr(from,"GOTO.BAK")) ||
           ((fault==20 || fault==21) && strstr(from,"GOTO.TMP")))return 0x27;
        return remove(from)?0x27:0;
    }
    abort();
}
int main(int argc,char** argv) {
    static struct A2fcApi api;
    static char full[81],other[81],note[80];static unsigned char buffer[512],type;
    static unsigned int aux;unsigned char loaded;
    fault=atoi(argv[2]);A=&api;N=note;
    api.full=full;api.other_full=other;api.copy_buf=buffer;api.filetype=&type;api.auxtype=&aux;
    api.fopen=open_file;api.fread=read_file;api.fwrite=write_file;api.fclose=close_file;
    api.strcpy=strcpy;api.strlen=strlen;api.mli=file_call;
    sprintf(cfg,"%s/GOTO.CFG",argv[1]);sprintf(temp,"%s/GOTO.TMP",argv[1]);sprintf(backup,"%s/GOTO.BAK",argv[1]);
    loaded=load();
    if(loaded){count=2;strcpy(slot(0),"/V/NEW");strcpy(slot(1),"/V/SECOND");save(NONE);}
    printf("%u|%s\n",loaded,N);return 0;
}
'''


class GotoSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='goto-test-', dir='/tmp')
        cls.root = Path(cls.tmp.name)
        c = cls.root / 'test.c'; c.write_text(HARNESS)
        cls.exe = cls.root / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(c), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, fault=0, reserved=None, missing=False):
        with tempfile.TemporaryDirectory(prefix='g-', dir='/tmp') as folder:
            p = Path(folder); cfg=p/'GOTO.CFG'; tmp=p/'GOTO.TMP'; bak=p/'GOTO.BAK'
            old=b'/V/OLD\r/V/KEEP\r'; new=b'/V/NEW\r/V/SECOND\r'
            if not missing: cfg.write_bytes(old)
            if reserved: (p/reserved).write_bytes(b'previous recovery')
            result=subprocess.check_output([self.exe,p,str(fault)],text=True).strip()
            success=fault in (0,19) and reserved is None
            if fault in (18,28):
                if fault==18:self.assertFalse(cfg.exists())
                else:self.assertEqual(cfg.read_bytes(),b'late arrival')
                self.assertEqual(bak.read_bytes(),old)
                self.assertEqual(tmp.read_bytes(),new)
            else:
                self.assertEqual(cfg.read_bytes(),new if success else old)
                if reserved: self.assertEqual((p/reserved).read_bytes(),b'previous recovery')
                if fault in (17,21,27,29):self.assertEqual(tmp.read_bytes(),new)
                elif fault==20:self.assertEqual(tmp.read_bytes(),new[:len(new)//2])
                elif reserved!='GOTO.TMP': self.assertFalse(tmp.exists())
                if fault==19: self.assertEqual(bak.read_bytes(),old)
                elif fault==29:self.assertEqual(bak.read_bytes(),b'late arrival')
                elif reserved!='GOTO.BAK': self.assertFalse(bak.exists())
            if fault in (17,18,20,21,27,28,29):
                self.assertIn('GOTO.TMP kept',result)
                before={f.name:f.read_bytes() for f in p.iterdir()}
                subprocess.check_output([self.exe,p,'0'],text=True)
                self.assertEqual({f.name:f.read_bytes() for f in p.iterdir()},before)
            return result

    def test_complete_verified_save(self): self.run_case()
    def test_missing_configuration_can_be_created(self): self.run_case(missing=True)
    def test_failed_load_never_becomes_an_empty_list(self):
        for fault in (1,2,3,4):
            with self.subTest(fault=fault): self.assertTrue(self.run_case(fault).startswith('0|'))
    def test_write_readback_and_close_failures_preserve_preferences(self):
        for fault in (10,11,12,13,14,15,16,22):
            with self.subTest(fault=fault): self.run_case(fault)
    def test_install_and_restore_failures_keep_recovery_files(self):
        for fault in (17,18,19):
            with self.subTest(fault=fault): self.run_case(fault)
    def test_recovery_name_collisions_are_preserved(self):
        for reserved in ('GOTO.TMP','GOTO.BAK'):
            with self.subTest(reserved=reserved): self.run_case(reserved=reserved)

    def test_destination_metadata_and_protections_refuse_before_create(self):
        for fault in (23,24,25,26):
            with self.subTest(fault=fault):self.run_case(fault)

    def test_combined_failure_and_cleanup_failure_preserves_bytes_on_retry(self):
        for fault in (20,21):
            with self.subTest(fault=fault):self.run_case(fault)

    def test_rename_failures_and_late_collisions_preserve_recovery_files(self):
        for fault in (27,28,29):
            with self.subTest(fault=fault):self.run_case(fault)


if __name__ == '__main__':
    unittest.main()
