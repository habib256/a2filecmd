"""IMGCONV's real entry point: failed conversions never destroy either input."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS=PREFIX+r'''
#include <errno.h>
#include <sys/stat.h>
static unsigned char track[4096],keyboard,strobe;
#define TRACK track
#define KBD (&keyboard)
#define STROBE (&strobe)
#include "src/plugins/imgconv.c"
static int fault,opened;
static FILE* writing;
static unsigned char mli(unsigned char cmd,void* params) {
    char old[80],newpath[80];FILE* f;
    struct Param {unsigned char n;unsigned char* path;};
    unsigned char* p=((struct Param*)params)->path;
    memcpy(old,p+1,p[0]);old[p[0]]=0;
    if(cmd==0xC4) {
        struct stat st;
        if(fault==1)return 0x27;
        if(stat(old,&st))return errno==ENOENT?0x46:0x27;
        memset(replace_ip.result,0,15);replace_ip.result[0]=0xC3;replace_ip.result[4]=1;return 0;
    }
    if(cmd==0xC0) {
        if(fault==2){f=fopen(old,"wb");fputs("new arrival",f);fclose(f);}
        f=fopen(old,"wx");if(!f)return 0x47;fclose(f);return 0;
    }
    if(cmd==0xC2) {
        p=replace_rn.newpath;memcpy(newpath,p+1,p[0]);newpath[p[0]]=0;
        if((fault==6 || fault==7) && strstr(old,"IMGCONV.TMP"))return 0x27;
        if(fault==7 && strstr(old,"A2FC.BAK"))return 0x27;
        f=fopen(newpath,"rb");if(f){fclose(f);return 0x47;}
        return rename(old,newpath)?0x27:0;
    }
    abort();
}
static FILE* open_file(const char* path,const char* mode) {
    FILE* f=fopen(path,mode);if(!strcmp(mode,"wb")){writing=f;opened=1;}return f;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    if(fault==3 && ftell(f)>=512)return 0;return fread(p,s,n,f);
}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f) {
    if(fault==4)return 0;return fwrite(p,s,n,f);
}
static int close_file(FILE* f) {int w=opened && f==writing;int r=fclose(f);if(w)opened=0;return fault==5 && w?-1:r;}
static char choose(void){return '2';}
static unsigned char yes(const char* p){return 1;}
static void message(const char* p){}
static void progress(const char* p,unsigned long n,unsigned long t){}
int main(int argc,char**argv) {
    static struct A2fcApi api;static struct Panel panels[2];static struct Entry e;
    static char source[64],dest[64],note[80],reselect[17];
    static unsigned char active,copy[512],type;static unsigned int aux;
    strcpy(panels[0].path,argv[1]);strcpy(panels[1].path,argv[2]);
    sprintf(source,"%s/INPUT.PO",argv[1]);strcpy(e.name,"INPUT.PO");e.size=8192;e.type=6;
    fault=atoi(argv[3]);if(fault==8)keyboard=0x9B;
    api.panels=panels;api.active=&active;api.selected=&e;api.full=source;api.other_full=dest;
    api.copy_buf=copy;api.note=note;api.reselect=reselect;api.filetype=&type;api.auxtype=&aux;
    api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;api.strcmp=strcmp;api.strlen=strlen;api.sprintf=sprintf;
    api.fopen=open_file;api.fclose=close_file;api.fread=read_file;api.fwrite=write_file;api.fseek=fseek;
    api.mli=mli;api.remove=remove;api.cgetc=choose;api.confirm=yes;api.message=message;api.progress_bar=progress;
    plugin_entry(&api);puts(note);return 0;
}
'''

class ImgconvSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='imgsafe-',dir='/tmp');cls.root=Path(cls.tmp.name)
        (cls.root/'test.c').write_text(HARNESS);cls.exe=cls.root/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.root/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.case=tempfile.TemporaryDirectory(prefix='io-',dir=self.root);self.addCleanup(self.case.cleanup)
        self.p=Path(self.case.name);self.s=self.p/'S';self.d=self.p/'D';self.s.mkdir();self.d.mkdir()
        self.src=self.s/'INPUT.PO';self.dst=self.d/'INPUT.2MG';self.data=bytes(range(256))*32
        self.src.write_bytes(self.data);self.dst.write_bytes(b'old image')
    def convert(self,fault=0):
        note=subprocess.check_output([self.exe,self.s,self.d,str(fault)],text=True)
        self.assertEqual(self.src.read_bytes(),self.data);return note
    def test_success_replaces_only_after_complete_conversion(self):
        self.assertIn(' -> ',self.convert())
        self.assertEqual(self.dst.read_bytes()[64:],self.data)
    def test_failures_preserve_old_image(self):
        for fault in (1,3,4,5,8):
            with self.subTest(fault=fault):
                self.assertNotIn(' -> ',self.convert(fault))
                self.assertEqual(self.dst.read_bytes(),b'old image')
    def test_rename_failure_restores_old_image(self):
        self.convert(6);self.assertEqual(self.dst.read_bytes(),b'old image')
        self.assertEqual((self.d/'IMGCONV.TMP').read_bytes()[64:],self.data)
    def test_failed_restore_preserves_old_image_in_backup(self):
        self.convert(7);self.assertEqual((self.d/'A2FC.BAK').read_bytes(),b'old image')
        self.assertEqual((self.d/'IMGCONV.TMP').read_bytes()[64:],self.data)
    def test_temporary_collision_is_untouched(self):
        tmp=self.d/'IMGCONV.TMP';tmp.write_bytes(b'previous recovery')
        self.convert();self.assertEqual(tmp.read_bytes(),b'previous recovery')
        self.assertEqual(self.dst.read_bytes(),b'old image')
    def test_destination_appearing_after_lookup_is_untouched(self):
        self.dst.unlink();self.convert(2);self.assertEqual(self.dst.read_bytes(),b'new arrival')
if __name__=='__main__':unittest.main()
