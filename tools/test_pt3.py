"""Real PT3 loader C: malformed headers, read/close failures, no hardware writes."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX,ROOT


def module():
    b=bytearray(220);b[:13]=b'ProTracker 3.';b[13]=ord('3')
    b[99:105]=bytes([1,6,1,0,203,0]);b[201:203]=bytes([0,255])
    b[107:109]=(209).to_bytes(2,'little');b[169:171]=(215).to_bytes(2,'little')
    b[203:209]=(217).to_bytes(2,'little')*3
    b[209:215]=bytes([0,1,0,0,0,0]);b[215:217]=bytes([0,1])
    return bytes(b)

HARNESS=PREFIX+r'''
static int fault,started,stopped,reads;
static size_t rd(void* p,size_t s,size_t n,FILE* f){++reads;return fread(p,s,n,f);}
static int ferr(FILE* f){return fault==1 || ferror(f);}
static int cls(FILE* f){int r=fclose(f);return fault==2?EOF:r;}
static FILE* opn(const char* p,const char* m){return fault==3?NULL:fopen(p,m);}
unsigned char host_song[4608];
#define ferror ferr
#include "src/plugins/pt3.c"
#undef ferror
unsigned int pt_end;
void __fastcall__ pt_tables(unsigned char* p){(void)p;}
unsigned char pt_init(void){return fault==4;}
unsigned char pt_frame(void){return 2;}
void __fastcall__ pt_hw_start(unsigned char slot){if(slot!=2)abort();started++;}
unsigned char pt_tick(void){return 1;}
void pt_output(void){}
void pt_silence(void){}
void pt_hw_stop(void){stopped++;}
static unsigned char mkey(unsigned char k){return k==27;}
static void info(const unsigned char* h){(void)h;}
static char key(void){return 0;}
static void cls_screen(void){}
static void puts_screen(const char* s){(void)s;}
int main(int argc,char**argv){
 static struct A2fcApi api;static struct Entry e;
 static unsigned char buf[512];static char note[80],sel[80];
 api.version=4;api.media_key=mkey;api.music_info=info;fault=atoi(argv[2]);api.arg=atoi(argv[3]);strcpy(e.name,"TEST.PT3");e.size=1;
 api.full=argv[1];api.selected=&e;api.note=note;api.reselect=sel;api.copy_buf=buf;
 api.fopen=opn;api.fread=rd;api.fclose=cls;api.strcpy=strcpy;api.cgetc=key;
 api.clrscr=cls_screen;api.cputs=puts_screen;
 plugin_entry(&api);printf("%d %d %s\n",started,stopped,note);return 0;
}
'''


class PT3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pt3-host-');cls.p=Path(cls.tmp.name)
        (cls.p/'test.c').write_text(HARNESS)
        cls.exe=cls.p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_data(self,data,good=False,fault=0,card=2):
        p=self.p/'source';p.write_bytes(data)
        out=subprocess.check_output([str(self.exe),str(p),str(fault),str(card)],text=True,timeout=5)
        self.assertTrue(out.startswith('1 1 ' if good else '0 0 '),out)
        self.assertEqual(p.read_bytes(),data)
    def test_valid_module_ignores_stale_panel_size(self):self.run_data(module(),True)
    def test_io_errors_and_no_card(self):
        for fault in (1,2,3,4):self.run_data(module(),fault=fault)
        self.run_data(module(),card=0)
    def test_truncated_and_oversized(self):
        b=module()
        for n in (0,12,13,100,200,201,202,208):self.run_data(b[:n])
        self.run_data(b+bytes(4609-len(b)))
    def test_header_and_order_bounds(self):
        for pos,value in ((0,0),(99,4),(99,0),(99,2),(99,3),(100,0),(101,0),(101,255),(102,1),(103,255),(104,255),(201,1),(201,255),(202,0),(107,0),(169,0)):
            b=bytearray(module());b[pos]=value;self.run_data(bytes(b))


if __name__=='__main__':unittest.main()
